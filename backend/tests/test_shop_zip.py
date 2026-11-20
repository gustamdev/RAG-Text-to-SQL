"""CEP -> endereço: cache, BrasilAPI, fallback ViaCEP, prefixo offline. Nenhum teste toca a rede (MockTransport)."""

import asyncio

import httpx
import pytest
from shop_helpers import V1, shop  # noqa: F401

from app.api.routes.shop_zip import get_zip_remote
from app.config import settings
from app.database.repos.geolocation import GeolocationRepo
from app.services import zip_lookup
from app.services.freight import FreightService
from app.services.zip_lookup import ZipRemote

Z = f"{V1}/shop/zip"
BRASIL = {
    "cep": "01310100", "state": "SP", "city": "São Paulo", "neighborhood": "Bela Vista", "street": "Avenida Paulista",
    "location": {"type": "Point", "coordinates": {"longitude": "-46.65", "latitude": "-23.56"}},
}  # fmt: skip
VIACEP = {
    "cep": "01310-100",
    "logradouro": "Avenida Paulista",
    "bairro": "Bela Vista",
    "localidade": "São Paulo",
    "uf": "SP",
}


class Net:
    """Transporte falso: `routes` mapeia host -> (status, json | exceção | bytes)."""

    def __init__(self, **routes):
        self.routes, self.calls = routes, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.host)
        status, body = self.routes[request.url.host]
        if isinstance(body, Exception):
            raise body
        if isinstance(body, bytes):
            return httpx.Response(status, content=body)
        return httpx.Response(status, json=body)

    def remote(self) -> ZipRemote:
        return ZipRemote(httpx.MockTransport(self))


@pytest.fixture
def zips(shop, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "ZIP_API_ENABLED", True)
    shop.run(
        shop.db["geolocation"].insert_one(
            {"geolocation_zip_code_prefix": "01310", "geolocation_city": "sao paulo", "geolocation_state": "SP"}
        )
    )

    def use(net: Net) -> Net:
        shop.client.app.dependency_overrides[get_zip_remote] = net.remote_instance = net.remote()
        remote = net.remote()
        shop.client.app.dependency_overrides[get_zip_remote] = lambda: remote
        return net

    shop.use = use
    return shop


def test_brasilapi_success(zips):
    net = zips.use(Net(**{"brasilapi.com.br": (200, BRASIL)}))
    r = zips.client.get(f"{Z}/01310100")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "zip": "01310100", "street": "Avenida Paulista", "district": "Bela Vista", "city": "São Paulo",
        "state": "SP", "lat": -23.56, "lng": -46.65, "source": "brasilapi",
    }  # fmt: skip
    assert r.headers["cache-control"] == "public, max-age=3600"
    assert net.calls == ["brasilapi.com.br"]


def test_cache_hit_no_second_call(zips):
    net = zips.use(Net(**{"brasilapi.com.br": (200, BRASIL)}))
    zips.client.get(f"{Z}/01310100")
    assert zips.client.get(f"{Z}/01310100").json()["source"] == "brasilapi"
    assert len(net.calls) == 1


def test_fallback_viacep(zips):
    net = zips.use(Net(**{"brasilapi.com.br": (404, {"message": "x"}), "viacep.com.br": (200, VIACEP)}))
    body = zips.client.get(f"{Z}/01310100").json()
    assert (body["source"], body["lat"], body["street"]) == ("viacep", None, "Avenida Paulista")
    assert net.calls == ["brasilapi.com.br", "viacep.com.br"]


def test_offline_when_apis_down(zips):
    zips.use(Net(**{"brasilapi.com.br": (500, {}), "viacep.com.br": (200, {"erro": True})}))
    r = zips.client.get(f"{Z}/01310999")
    assert r.json() == {
        "zip": "01310999", "street": None, "district": None, "city": "sao paulo", "state": "SP",
        "lat": None, "lng": None, "source": "offline",
    }  # fmt: skip
    assert r.headers["cache-control"] == "public, max-age=300"


def test_unknown_everywhere_404(zips):
    zips.use(Net(**{"brasilapi.com.br": (404, {}), "viacep.com.br": (200, {"erro": True})}))
    assert zips.client.get(f"{Z}/99999999").status_code == 404


@pytest.mark.parametrize(
    "bad",
    [
        b"<html>",
        b'["x"]',
        b'{"cep": "01310100", "city": 7, "state": "SP"}',
        b'{"cep": "99999999", "city": "a", "state": "SP"}',
    ],
)
def test_malformed_json_falls_back(zips, bad):
    zips.use(Net(**{"brasilapi.com.br": (200, bad), "viacep.com.br": (200, bad)}))
    assert zips.client.get(f"{Z}/01310100").json()["source"] == "offline"


def test_timeout_falls_back(zips):
    err = httpx.ConnectTimeout("t")
    zips.use(Net(**{"brasilapi.com.br": (0, err), "viacep.com.br": (0, err)}))
    assert zips.client.get(f"{Z}/01310100").json()["source"] == "offline"


def test_untrusted_text_sanitized(zips):
    evil = {
        **BRASIL,
        "street": "<script>" + "x" * 500,
        "neighborhood": "<>",
        "location": {"coordinates": {"latitude": 99}},
    }
    zips.use(Net(**{"brasilapi.com.br": (200, evil)}))
    body = zips.client.get(f"{Z}/01310100").json()
    assert len(body["street"]) == 100 and "<" not in body["street"]
    assert body["district"] is None and body["lat"] is None and body["lng"] is None


def test_circuit_breaker_skips_api_after_failures(zips):
    net = zips.use(Net(**{"brasilapi.com.br": (500, {}), "viacep.com.br": (404, {})}))
    for _ in range(zip_lookup.BREAKER_FAILS + 1):
        zips.client.get(f"{Z}/01310100")
    assert net.calls.count("brasilapi.com.br") == zip_lookup.BREAKER_FAILS


def test_api_disabled_is_offline_only(zips, monkeypatch):
    monkeypatch.setattr(settings, "ZIP_API_ENABLED", False)
    net = zips.use(Net())
    assert zips.client.get(f"{Z}/01310100").json()["source"] == "offline"
    assert net.calls == []


@pytest.mark.parametrize("bad", ["01310-100", "0131010", "013101000", "0131010a", "٠١٣١٠١٠٠"])
def test_bad_format_422(zips, bad):
    assert zips.client.get(f"{Z}/{bad}").status_code == 422


def test_strict_rate_limit(zips, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT", 8)  # balde do CEP = 8 // 4 = 2
    zips.use(Net(**{"brasilapi.com.br": (200, BRASIL)}))
    assert [zips.client.get(f"{Z}/01310100").status_code for _ in range(3)] == [200, 200, 429]


def test_freight_uses_real_coords_else_prefix(zips):
    zips.run(
        zips.db["geolocation"].update_one({}, {"$set": {"geolocation_lat": 0.0, "geolocation_lng": 0.0}})
    )  # origem
    zips.geo("10001", 0.0, 1.0)
    # coords reais do CEP (-23.56, -46.65) ficam a ~2.1 mil km da origem (0,0); prefixo daria 111 km
    real = Net(**{"brasilapi.com.br": (200, {**BRASIL, "cep": "10001000"})}).remote()
    prefix = Net(**{"brasilapi.com.br": (404, {}), "viacep.com.br": (404, {})}).remote()

    def price(remote):
        service = FreightService(GeolocationRepo(zips.db), remote)
        return asyncio.run(service.options("10001000", 1000))[0].price_cents

    assert price(prefix) == 2084  # mesmo valor do teste de frete só por prefixo
    assert price(real) > 2084


def test_access_log_masks_zip():
    import logging

    from app.core.logging import MaskZipFilter

    rec = logging.LogRecord(
        "uvicorn.access",
        20,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4", "GET", "/api/v1/shop/zip/01310100", "1.1", 200),
        None,
    )
    MaskZipFilter().filter(rec)
    assert "01310100" not in rec.getMessage() and "/shop/zip/XXXXX***" in rec.getMessage()


def test_negative_cache_and_error_no_store(zips):
    net = zips.use(Net(**{"brasilapi.com.br": (404, {}), "viacep.com.br": (200, {"erro": True})}))
    for _ in range(2):
        r = zips.client.get(f"{Z}/99999999")
        assert r.status_code == 404 and r.headers["cache-control"] == "no-store"
    assert len(net.calls) == 2  # segunda consulta veio do cache negativo
    assert zips.client.get(f"{Z}/0131010").headers["cache-control"] == "no-store"  # 422


def test_outage_not_negative_cached(zips):
    net = zips.use(Net(**{"brasilapi.com.br": (500, {}), "viacep.com.br": (500, {})}))
    for _ in range(2):
        assert zips.client.get(f"{Z}/99999999").status_code == 404
    assert len(net.calls) == 4


def test_429_has_no_store(zips, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT", 4)
    zips.use(Net(**{"brasilapi.com.br": (200, BRASIL)}))
    codes = [zips.client.get(f"{Z}/01310100") for _ in range(2)]
    assert (codes[1].status_code, codes[1].headers["cache-control"]) == (429, "no-store")


def test_oversized_body_aborted(zips):
    zips.use(Net(**{"brasilapi.com.br": (200, b"x" * (zip_lookup.MAX_BODY + 1)), "viacep.com.br": (200, VIACEP)}))
    assert zips.client.get(f"{Z}/01310100").json()["source"] == "viacep"


def test_single_flight_one_external_call():
    net = Net(**{"brasilapi.com.br": (200, BRASIL)})
    remote = net.remote()

    async def run():
        return await asyncio.gather(*(remote.fetch("01310100") for _ in range(5)))

    settings.ZIP_API_ENABLED = True
    try:
        got = asyncio.run(run())
    finally:
        settings.ZIP_API_ENABLED = False
    assert all(g and g.source == "brasilapi" for g in got) and len(net.calls) == 1
