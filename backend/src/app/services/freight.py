"""Frete offline por localização (demo). Sem API externa e sem guardar coordenada do cliente.

Modelo (centavos, funções puras e determinísticas):
    standard = min(CAP, BASE + PER_KG * kg + PER_KM * km)      economy = 80% do standard
    km       = haversine entre o prefixo de CEP (5 dígitos) do depósito e o do destino (coleção `geolocation`)
    prazo    = faixa de dias úteis por distância (WINDOWS); economy soma ECONOMY_EXTRA_DAYS
Prefixo de CEP é impreciso (a coordenada é a média do prefixo): serve para demo, não para cobrança real.
CEP sem coordenada: com UF conhecida usa FALLBACK_KM (distância fixa aproximada a partir de São Paulo,
a origem padrão; se SHOP_ORIGIN_ZIP_PREFIX mudar, a tabela deixa de refletir o depósito); sem UF, o CEP é inválido.
"""

from math import asin, cos, radians, sin, sqrt

from app.config import settings
from app.core.errors import DomainError, ServiceUnavailable
from app.database.repos.geolocation import GeolocationRepo
from app.schemas.shop_store import FreightOption

EARTH_KM = 6371.0
BASE_CENTS = 1500
PER_KG_CENTS = 250
PER_KM_CENTS = 3  # R$ 0,03 por km
CAP_CENTS = 12000
DEFAULT_WEIGHT_G = 500  # produto sem peso cadastrado
ECONOMY_PCT = 80
ECONOMY_EXTRA_DAYS = (3, 4)  # (min, max) a mais
WINDOWS = ((100, 2, 3), (500, 3, 5), (1000, 4, 7), (2000, 6, 10))  # (até km, dias_min, dias_max)
FAR_WINDOW = (9, 15)
FALLBACK_KM = {
    "SP": 100, "RJ": 430, "MG": 590, "ES": 880, "PR": 410, "SC": 700, "RS": 1130, "DF": 870, "GO": 900,
    "MS": 870, "MT": 1600, "BA": 1960, "SE": 1960, "AL": 2000, "PE": 2130, "PB": 2300, "RN": 2440,
    "CE": 2370, "PI": 2200, "MA": 2260, "TO": 1500, "PA": 2400, "AP": 2700, "AM": 2700, "RR": 3300,
    "RO": 2400, "AC": 3100,
}  # fmt: skip

INVALID_ZIP = "CEP inválido."


class InvalidZip(DomainError):
    status_code = 422

    def __init__(self):
        super().__init__(INVALID_ZIP)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * EARTH_KM * asin(sqrt(a))


def quote(distance_km: float, weight_g: float) -> list[FreightOption]:
    standard = min(CAP_CENTS, BASE_CENTS + round(weight_g * PER_KG_CENTS / 1000) + round(distance_km * PER_KM_CENTS))
    days_min, days_max = next(((lo, hi) for km, lo, hi in WINDOWS if distance_km <= km), FAR_WINDOW)
    return [
        FreightOption(code="standard", label="Padrão", price_cents=standard, days_min=days_min, days_max=days_max),
        FreightOption(
            code="economy",
            label="Econômico",
            price_cents=round(standard * ECONOMY_PCT / 100),
            days_min=days_min + ECONOMY_EXTRA_DAYS[0],
            days_max=days_max + ECONOMY_EXTRA_DAYS[1],
        ),
    ]


class FreightService:
    def __init__(self, geo: GeolocationRepo):
        self.geo = geo

    async def options(self, zip8: str, weight_g: float, state: str | None = None) -> list[FreightOption]:
        """InvalidZip (422) se o CEP não tem coordenada e não há UF para o fallback."""
        dest = await self.geo.coords(zip8[:5])
        if dest is not None:
            origin = await self.geo.coords(settings.SHOP_ORIGIN_ZIP_PREFIX)
            if origin is None:
                raise ServiceUnavailable("Frete indisponível no momento.")
            return quote(haversine_km(*origin, *dest), weight_g)
        if state in FALLBACK_KM:
            return quote(FALLBACK_KM[state], weight_g)
        raise InvalidZip
