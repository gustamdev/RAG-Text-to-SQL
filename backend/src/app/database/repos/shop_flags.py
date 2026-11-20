from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now


class ShopFlagRepo:
    """Marcadores de trabalho pendente que sobrevivem a restart (ex.: refresh do snapshot após exclusão)."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_flags"]

    async def set(self, name: str) -> None:
        await self.col.update_one({"_id": name}, {"$set": {"at": now()}}, upsert=True)

    async def clear(self, name: str) -> None:
        await self.col.delete_one({"_id": name})

    async def is_set(self, name: str) -> bool:
        return await self.col.find_one({"_id": name}) is not None
