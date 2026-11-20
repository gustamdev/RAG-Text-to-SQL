"""CEP real consultado NO SERVIDOR (o navegador nunca chama API externa): cache, BrasilAPI, ViaCEP, prefixo offline.

Só o CEP sai para BrasilAPI/ViaCEP, sem identificar o cliente (UA genérico, sem cookies). Texto das APIs é dado não
confiável: tipos checados, `<`/`>`/controle removidos e tamanho truncado. Sem redirects. O CEP completo não é logado.
shortcut: cache e circuit-breaker vivem na memória do processo, não são compartilhados entre réplicas.
"""

import asyncio
import json
import logging
import re
import time
from collections import OrderedDict

import httpx

from app.config import settings
from app.database.repos.geolocation import GeolocationRepo
from app.schemas.shop_store import ZipOut

logger = logging.getLogger(__name__)

TIMEOUT_S = 3.0
CACHE_TTL_S = 7 * 86400
NEG_TTL_S = 600.0  # CEP que nenhuma fonte conhece
CACHE_MAX = 5000
NEG_MAX = 5000
BREAKER_FAILS = 3
BREAKER_PAUSE_S = 60.0
MAX_BODY = 16_384
USER_AGENT = "zip-lookup/1.0"
_UNSAFE = re.compile(r"[<>\x00-\x1f\x7f]")
_UF = re.compile(r"^[A-Z]{2}$")


def _txt(value, limit: int = 100) -> str | None:
    if not isinstance(value, str):
        return None
    return _UNSAFE.sub("", value).strip()[:limit] or None


def _num(value, lo: float, hi: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if lo <= number <= hi else None  # NaN falha na comparação


def _build(zip8: str, cep, street, district, city, state, lat, lng, source: str) -> ZipOut | None:
    """None se o CEP devolvido difere do pedido ou cidade/UF não são válidas."""
    city, state = _txt(city), _txt(state, 2)
    if (
        not isinstance(cep, str)
        or re.sub(r"\D", "", cep) != zip8
        or city is None
        or not state
        or not _UF.match(state.upper())
    ):
        return None
    lat, lng = _num(lat, -34.0, 6.0), _num(lng, -74.0, -28.0)  # caixa do Brasil
    if lat is None or lng is None:
        lat = lng = None
    return ZipOut(
        zip=zip8, street=_txt(street), district=_txt(district), city=city, state=state.upper(),
        lat=lat, lng=lng, source=source,
    )  # fmt: skip


def parse_brasilapi(zip8: str, data) -> ZipOut | None:
    if not isinstance(data, dict):
        return None
    coords = (data.get("location") or {}).get("coordinates") if isinstance(data.get("location"), dict) else None
    coords = coords if isinstance(coords, dict) else {}
    return _build(
        zip8, data.get("cep"), data.get("street"), data.get("neighborhood"), data.get("city"), data.get("state"),
        coords.get("latitude"), coords.get("longitude"), "brasilapi",
    )  # fmt: skip


def parse_viacep(zip8: str, data) -> ZipOut | None:
    if not isinstance(data, dict) or data.get("erro"):
        return None
    return _build(
        zip8, data.get("cep"), data.get("logradouro"), data.get("bairro"), data.get("localidade"), data.get("uf"),
        None, None, "viacep",
    )  # fmt: skip


SOURCES = (
    ("brasilapi", "https://brasilapi.com.br/api/cep/v2/{}", parse_brasilapi),
    ("viacep", "https://viacep.com.br/ws/{}/json/", parse_viacep),
)


class ZipRemote:
    """Cache LRU com TTL + circuit-breaker por API. `transport` só para testes (httpx.MockTransport)."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.transport = transport
        self._cache: OrderedDict[str, tuple[float, ZipOut]] = OrderedDict()
        self._fails: dict[str, int] = {}
        self._paused_until: dict[str, float] = {}
        self._neg: OrderedDict[str, float] = OrderedDict()
        self._inflight: dict[str, asyncio.Future] = {}  # single-flight por CEP

    def _cached(self, zip8: str) -> ZipOut | None:
        hit = self._cache.get(zip8)
        if hit is None or time.monotonic() - hit[0] > CACHE_TTL_S:
            self._cache.pop(zip8, None)
            return None
        self._cache.move_to_end(zip8)
        return hit[1]

    def _store(self, info: ZipOut) -> None:
        self._cache[info.zip] = (time.monotonic(), info)
        while len(self._cache) > CACHE_MAX:
            self._cache.popitem(last=False)

    def _fail(self, name: str, reason: str) -> None:
        self._fails[name] = self._fails.get(name, 0) + 1
        if self._fails[name] >= BREAKER_FAILS:
            self._paused_until[name] = time.monotonic() + BREAKER_PAUSE_S
            self._fails[name] = 0
        logger.warning("CEP: %s falhou (%s)", name, reason)

    async def _ask(
        self, client: httpx.AsyncClient, name: str, url: str, parse, zip8: str
    ) -> tuple[ZipOut | None, bool]:
        """(info, falhou). 404 = CEP desconhecido (não é falha); 429/5xx/timeout/corpo ruim contam falha.
        shortcut: 429 da API pausa 60 s como qualquer falha, sem backoff próprio; refinar se virar rotina."""
        if time.monotonic() < self._paused_until.get(name, 0):
            return None, True
        try:
            async with client.stream("GET", url.format(zip8)) as response:
                if response.status_code == 404:
                    self._fails[name] = 0
                    return None, False
                if response.status_code != 200:
                    return self._fail(name, f"status {response.status_code}"), True
                body = b""
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BODY:  # aborta sem baixar o resto
                        return self._fail(name, "corpo grande"), True
            info = parse(zip8, json.loads(body))
        except (httpx.HTTPError, ValueError) as exc:
            return self._fail(name, type(exc).__name__), True
        self._fails[name] = 0
        return info, False

    async def _query(self, zip8: str) -> ZipOut | None:
        failed = False
        async with httpx.AsyncClient(
            timeout=TIMEOUT_S, follow_redirects=False, headers={"User-Agent": USER_AGENT}, transport=self.transport
        ) as client:
            for name, url, parse in SOURCES:
                info, bad = await self._ask(client, name, url, parse, zip8)
                if info:
                    self._store(info)
                    return info
                failed = failed or bad
        if not failed:  # só cacheia "desconhecido" se todas as fontes responderam; queda não envenena o cache
            self._neg[zip8] = time.monotonic() + NEG_TTL_S
            while len(self._neg) > NEG_MAX:
                self._neg.popitem(last=False)
        return None

    async def fetch(self, zip8: str) -> ZipOut | None:
        """Informação de uma API real (cacheada) ou None. Nunca levanta por falha de rede."""
        if not settings.ZIP_API_ENABLED:
            return None
        if (hit := self._cached(zip8)) is not None:
            return hit
        if self._neg.get(zip8, 0) > time.monotonic():
            return None
        if (pending := self._inflight.get(zip8)) is not None:
            return await asyncio.shield(pending)
        future = self._inflight[zip8] = asyncio.get_running_loop().create_future()
        result = None
        try:
            result = await self._query(zip8)
            return result
        finally:
            del self._inflight[zip8]
            future.set_result(result)


zip_remote = ZipRemote()


async def lookup_zip(zip8: str, geo: GeolocationRepo, remote: ZipRemote) -> ZipOut | None:
    if info := await remote.fetch(zip8):
        return info
    found = await geo.city_state(zip8[:5])
    return ZipOut(zip=zip8, city=found[0], state=found[1], source="offline") if found else None
