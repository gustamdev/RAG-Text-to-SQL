"""E4: frete offline (haversine por prefixo de CEP) e endereços."""

import pytest
from shop_helpers import V1, shop  # noqa: F401

from app.services.freight import CAP_CENTS, haversine_km, quote

A = f"{V1}/shop/account/addresses"
PF = f"{V1}/shop/products"
CF = f"{V1}/shop/cart"

# Origem 01310 = (0, 0). Na linha do Equador 1 grau de longitude = 2*pi*6371/360 = 111,1949 km.
# Pares de CEP e o valor esperado, conferido à mão para peso 1000 g (250 c) e R$ 0,03/km:
#   10001 (0,1):  d = 111,19 km  -> 1500 + 250 + round(333,58)=334   = 2084 | faixa <=500 km: 3-5 dias
#   10002 (0,5):  d = 555,97 km  -> 1500 + 250 + round(1667,92)=1668 = 3418 | faixa <=1000 km: 4-7 dias
#   10003 (0,20): d = 2223,90 km -> 1500 + 250 + round(6671,69)=6672 = 8422 | faixa > 2000 km: 9-15 dias
# Econômico = round(80% do padrão), prazo +3/+4 dias.
FIXED = [
    ("10001000", 2084, (3, 5), 1667, (6, 9)),
    ("10002000", 3418, (4, 7), 2734, (7, 11)),
    ("10003000", 8422, (9, 15), 6738, (12, 19)),
]


@pytest.fixture
def fr(shop):  # noqa: F811
    shop.geo("01310", 0.0, 0.0)
    shop.geo("10001", 0.0, 1.0)
    shop.geo("10002", 0.0, 5.0)
    shop.geo("10003", 0.0, 20.0)
    shop.geo("10004", 0.0, 60.0)
    shop.product("p-1kg", price_cents=1000, stock=9, weight_g=1000.0)
    shop.product("p-noweight", price_cents=1000, stock=9, weight_g=None)
    shop.login("cust-a")
    return shop


def opts(response) -> dict:
    assert response.status_code == 200, response.text
    return {o["code"]: o for o in response.json()["options"]}


def test_haversine_known_values():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.1949, abs=1e-3)
    assert haversine_km(0, 0, 0, 0) == 0
    assert haversine_km(10, 20, -5, 33) == pytest.approx(haversine_km(-5, 33, 10, 20))


@pytest.mark.parametrize(("zip8", "std", "std_days", "eco", "eco_days"), FIXED)
def test_freight_fixed_zips(fr, zip8, std, std_days, eco, eco_days):
    got = opts(fr.client.get(f"{PF}/p-1kg/freight", params={"zip": zip8}))
    assert (got["standard"]["price_cents"], (got["standard"]["days_min"], got["standard"]["days_max"])) == (
        std,
        std_days,
    )
    assert (got["economy"]["price_cents"], (got["economy"]["days_min"], got["economy"]["days_max"])) == (eco, eco_days)


def test_freight_deterministic_and_zip_normalized(fr):
    first = fr.client.get(f"{PF}/p-1kg/freight", params={"zip": "10002-000"}).json()
    assert first["zip"] == "10002000"
    assert fr.client.get(f"{PF}/p-1kg/freight", params={"zip": "10002000"}).json() == first
    assert quote(555.97, 1000) == quote(555.97, 1000)


def test_freight_weight_and_cap(fr):
    assert quote(0, 2500)[0].price_cents == 1500 + 625  # 2,5 kg * 250
    assert quote(0, 0)[0].price_cents == 1500
    assert quote(99999, 1000)[0].price_cents == CAP_CENTS
    # produto sem peso conta 500 g (125 c)
    got = opts(fr.client.get(f"{PF}/p-noweight/freight", params={"zip": "10001000"}))
    assert got["standard"]["price_cents"] == 1500 + 125 + 334


def test_freight_invalid_zip_and_unknown(fr):
    for bad in ("123", "1234567a", "123456789"):
        assert fr.client.get(f"{PF}/p-1kg/freight", params={"zip": bad}).status_code == 422
    r = fr.client.get(f"{PF}/p-1kg/freight", params={"zip": "99999999"})  # sem coordenada e sem UF
    assert (r.status_code, r.json()) == (422, {"detail": "CEP inválido."})
    assert fr.client.get(f"{PF}/nao-existe/freight", params={"zip": "10001000"}).status_code == 404


def test_freight_origin_missing_is_503(shop):  # noqa: F811
    shop.geo("10001", 0.0, 1.0)
    shop.product("p", weight_g=1000.0)
    assert shop.client.get(f"{PF}/p/freight", params={"zip": "10001000"}).status_code == 503


def test_freight_does_not_store_customer_coordinates(fr):
    before = fr.run(fr.db["geolocation"].count_documents({}))
    fr.client.get(f"{PF}/p-1kg/freight", params={"zip": "10001000"})
    assert fr.run(fr.db["geolocation"].count_documents({})) == before
    assert sorted(fr.run(fr.db.list_collection_names())) == ["geolocation", "shop_products"]


# --- carrinho ---------------------------------------------------------------------------------


def test_cart_freight_sums_weight(fr):
    r = fr.client.post(f"{CF}/freight", json={"zip": "10001000"})
    assert (r.status_code, r.json()) == (409, {"detail": "Carrinho vazio."})
    fr.client.post(f"{CF}/items", json={"product_id": "p-1kg", "qty": 2})
    fr.client.post(f"{CF}/items", json={"product_id": "p-noweight", "qty": 1})  # 2000 + 500 = 2500 g
    expected = 1500 + 625 + 334
    assert opts(fr.client.post(f"{CF}/freight", json={"zip": "10001-000"}))["standard"]["price_cents"] == expected
    assert opts(fr.client.get(f"{CF}/freight", params={"zip": "10001000"}))["standard"]["price_cents"] == expected


def test_cart_freight_by_address_and_uf_fallback(fr):
    fr.client.post(f"{CF}/items", json={"product_id": "p-1kg", "qty": 1})
    known = fr.client.post(A, json={"label": "Casa", "zip": "10002000", "city": "X", "state": "sp"}).json()
    assert opts(fr.client.post(f"{CF}/freight", json={"address_id": known["id"]}))["standard"]["price_cents"] == 3418
    unknown = fr.client.post(A, json={"label": "Sítio", "zip": "99999999", "city": "Manaus", "state": "AM"}).json()
    got = opts(fr.client.post(f"{CF}/freight", json={"address_id": unknown["id"]}))
    assert got["standard"]["price_cents"] == 1500 + 250 + 8100  # fallback AM = 2700 km fixos
    assert (got["standard"]["days_min"], got["standard"]["days_max"]) == (9, 15)
    assert fr.client.post(f"{CF}/freight", json={"zip": "99999999"}).status_code == 422


def test_cart_freight_body_validation(fr):
    fr.client.post(f"{CF}/items", json={"product_id": "p-1kg", "qty": 1})
    assert fr.client.post(f"{CF}/freight", json={}).status_code == 422
    assert fr.client.post(f"{CF}/freight", json={"zip": "10001000", "address_id": "x"}).status_code == 422
    assert fr.client.post(f"{CF}/freight", json={"zip": "abc"}).status_code == 422


def test_cart_freight_foreign_address_404(fr):
    fr.client.post(f"{CF}/items", json={"product_id": "p-1kg", "qty": 1})
    mine = fr.client.post(A, json={"label": "Casa", "zip": "10001000", "city": "X", "state": "SP"}).json()
    fr.login("cust-b")
    fr.client.post(f"{CF}/items", json={"product_id": "p-1kg", "qty": 1})
    assert fr.client.post(f"{CF}/freight", json={"address_id": mine["id"]}).status_code == 404


# --- endereços --------------------------------------------------------------------------------

BASE = {"label": "Casa", "zip": "01310100", "city": "São Paulo", "state": "SP"}


def test_address_create_defaults_and_fields(fr):
    r = fr.client.post(A, json={**BASE, "street": "Av. Paulista", "number": "1000", "recipient": "Ana"})
    assert r.status_code == 201
    body = r.json()
    assert body["is_default"] is True and body["street"] == "Av. Paulista" and body["complement"] is None
    assert fr.client.post(A, json={**BASE, "label": "Trabalho"}).json()["is_default"] is False
    assert [a["label"] for a in fr.client.get(A).json()] == ["Casa", "Trabalho"]


def test_address_limit(fr):
    for i in range(3):
        assert fr.client.post(A, json={**BASE, "label": f"E{i}"}).status_code == 201
    r = fr.client.post(A, json=BASE)
    assert (r.status_code, r.json()) == (409, {"detail": "Limite de 3 endereços atingido."})
    fr.login("cust-b")  # o limite é por cliente
    assert fr.client.post(A, json=BASE).status_code == 201


@pytest.mark.parametrize(
    "bad",
    [
        {"zip": "1234567"}, {"zip": "123456789"}, {"zip": "0131010a"}, {"zip": "01310-100"}, {"zip": ""},
        {"state": "XX"}, {"state": "S"}, {"label": ""}, {"label": "x" * 31}, {"city": ""},
        {"phone": "11999999999"}, {"cpf": "12345678900"}, {"is_default": "talvez"},
    ],
)  # fmt: skip
def test_address_invalid_rejected(fr, bad):
    assert fr.client.post(A, json={**BASE, **bad}).status_code == 422
    assert fr.client.get(A).json() == []


def test_address_missing_required_rejected(fr):
    for key in ("label", "zip", "city", "state"):
        assert fr.client.post(A, json={k: v for k, v in BASE.items() if k != key}).status_code == 422


def test_address_patch_and_default_switch(fr):
    first = fr.client.post(A, json=BASE).json()
    second = fr.client.post(A, json={**BASE, "label": "Outro"}).json()
    r = fr.client.patch(f"{A}/{second['id']}", json={"is_default": True, "city": "Santos"})
    assert r.status_code == 200 and r.json()["city"] == "Santos"
    assert {a["label"]: a["is_default"] for a in fr.client.get(A).json()} == {"Casa": False, "Outro": True}
    assert fr.client.patch(f"{A}/{first['id']}", json={"state": "rj"}).json()["state"] == "RJ"
    for bad in ({}, {"label": None}, {"state": "ZZ"}, {"zip": "12"}, {"customer_id": "x"}, {"phone": "1"}):
        assert fr.client.patch(f"{A}/{first['id']}", json=bad).status_code == 422


def test_address_delete_promotes_default(fr):
    a = fr.client.post(A, json=BASE).json()
    fr.client.post(A, json={**BASE, "label": "Outro"})
    assert fr.client.delete(f"{A}/{a['id']}").status_code == 204
    left = fr.client.get(A).json()
    assert [(x["label"], x["is_default"]) for x in left] == [("Outro", True)]
    assert fr.client.delete(f"{A}/{a['id']}").status_code == 404


def test_address_idor_is_404(fr):
    mine = fr.client.post(A, json=BASE).json()
    fr.login("cust-b")
    assert fr.client.get(A).json() == []
    assert fr.client.patch(f"{A}/{mine['id']}", json={"city": "Hack"}).status_code == 404
    assert fr.client.delete(f"{A}/{mine['id']}").status_code == 404
    assert fr.client.patch(f"{A}/nao-existe", json={"city": "x"}).status_code == 404  # mesmo 404 do inexistente
    fr.login("cust-a")
    assert fr.client.get(A).json()[0]["city"] == "São Paulo"


def test_address_requires_customer(fr):
    from app.api.shop_deps import get_current_customer

    fr.client.app.dependency_overrides.pop(get_current_customer)
    assert fr.client.get(A).status_code == 401
