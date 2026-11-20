from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.timeutil import now


class ShopCartRepo:
    """Toda query filtra por customer_id (um carrinho por cliente: o id do cliente é a chave)."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_carts"]

    async def get(self, customer_id: str) -> dict | None:
        return await self.col.find_one({"customer_id": customer_id})

    async def save(self, customer_id: str, items: list[dict], rev: int | None) -> bool:
        """Escrita otimista: `rev` é a revisão lida (None = carrinho ainda não existe). False = outra requisição
        gravou no meio; quem chama relê e refaz (sem perder item de aba paralela)."""
        if rev is None:
            try:
                await self.col.insert_one({"customer_id": customer_id, "items": items, "updated_at": now(), "rev": 1})
            except DuplicateKeyError:
                return False
            return True
        res = await self.col.update_one(
            {"customer_id": customer_id, "rev": rev},
            {"$set": {"items": items, "updated_at": now()}, "$inc": {"rev": 1}},
        )
        return res.matched_count == 1

    async def clear(self, customer_id: str) -> None:
        await self.col.delete_one({"customer_id": customer_id})

    async def remove(self, customer_id: str, product_ids: list[str]) -> None:
        """Tira só os itens do pedido pago: o que foi adicionado depois fica no carrinho."""
        await self.col.update_one(
            {"customer_id": customer_id},
            {"$pull": {"items": {"product_id": {"$in": product_ids}}}, "$inc": {"rev": 1}},
        )
