from pymongo.asynchronous.database import AsyncDatabase


class ShopStockRepo:
    """Estoque em shop_products sem transação (Mongo standalone): decremento condicional atômico por item."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_products"]

    async def reserve(self, product_id: str, qty: int) -> bool:
        """True se havia estoque (`$gte`) e o decremento foi aplicado; o estoque nunca fica < 0."""
        doc = await self.col.find_one_and_update(
            {"product_id": product_id, "stock": {"$gte": qty}}, {"$inc": {"stock": -qty}}, projection={"_id": 1}
        )
        return doc is not None

    async def release(self, product_id: str, qty: int) -> None:
        await self.col.update_one({"product_id": product_id}, {"$inc": {"stock": qty}})
