from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now


class ShopCartRepo:
    """Toda query filtra por customer_id (um carrinho por cliente: o id do cliente é a chave)."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_carts"]

    async def get(self, customer_id: str) -> dict | None:
        return await self.col.find_one({"customer_id": customer_id})

    async def save(self, customer_id: str, items: list[dict]) -> None:
        # shortcut: leitura-modificação-escrita sem lock; só o próprio cliente corre contra si mesmo.
        await self.col.update_one(
            {"customer_id": customer_id},
            {"$set": {"items": items, "updated_at": now()}, "$setOnInsert": {"customer_id": customer_id}},
            upsert=True,
        )

    async def clear(self, customer_id: str) -> None:
        await self.col.delete_one({"customer_id": customer_id})
