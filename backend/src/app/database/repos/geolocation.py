from pymongo.asynchronous.database import AsyncDatabase


class GeolocationRepo:
    """Coleção `geolocation` do Olist: 1 doc por prefixo de CEP (lat/lng já médias). Só leitura."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["geolocation"]

    async def coords(self, zip_prefix: str) -> tuple[float, float] | None:
        doc = await self.col.find_one(
            {"geolocation_zip_code_prefix": zip_prefix}, {"geolocation_lat": 1, "geolocation_lng": 1}
        )
        if not doc or doc.get("geolocation_lat") is None or doc.get("geolocation_lng") is None:
            return None
        return float(doc["geolocation_lat"]), float(doc["geolocation_lng"])

    async def city_state(self, zip_prefix: str) -> tuple[str, str] | None:
        doc = await self.col.find_one(
            {"geolocation_zip_code_prefix": zip_prefix}, {"geolocation_city": 1, "geolocation_state": 1}
        )
        if not doc or not doc.get("geolocation_city") or not doc.get("geolocation_state"):
            return None
        return str(doc["geolocation_city"]), str(doc["geolocation_state"])
