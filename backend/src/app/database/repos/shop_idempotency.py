from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.timeutil import now


class ShopIdempotencyRepo:
    """`(customer_id, scope, key)` único: quem insere primeiro (claim) é o único que executa a operação."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_idempotency"]

    async def claim(self, customer_id: str, scope: str, key: str, body_hash: str) -> dict | None:
        """None se a chave foi reservada agora; senão o registro existente (status_code None = em andamento)."""
        ident = {"customer_id": customer_id, "scope": scope, "key": key}
        try:
            await self.col.insert_one(
                {**ident, "body_hash": body_hash, "status_code": None, "response": None, "created_at": now()}
            )
        except DuplicateKeyError:
            return await self.col.find_one(ident)
        return None

    async def complete(self, customer_id: str, scope: str, key: str, status_code: int, response: dict) -> None:
        await self.col.update_one(
            {"customer_id": customer_id, "scope": scope, "key": key},
            {"$set": {"status_code": status_code, "response": response}},
        )

    async def release(self, customer_id: str, scope: str, key: str) -> None:
        """Libera a chave de uma execução que falhou (erro, 504): repetir reexecuta."""
        await self.col.delete_one({"customer_id": customer_id, "scope": scope, "key": key, "status_code": None})
