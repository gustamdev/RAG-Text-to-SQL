import uuid
from datetime import timedelta

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.timeutil import now

STALE_S = 300  # > qualquer timeout do gateway; claim sem resposta há mais que isso = processo morreu, retomável


class ShopIdempotencyRepo:
    """`(customer_id, scope, key)` único: quem insere primeiro (claim) é o único que executa a operação."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_idempotency"]

    async def claim(self, customer_id: str, scope: str, key: str, body_hash: str) -> tuple[dict | None, str]:
        """(None, token) se a chave foi reservada agora; senão (registro existente, "").
        O token amarra complete/release ao dono do claim: execução lenta que perdeu o claim não sobrescreve."""
        ident = {"customer_id": customer_id, "scope": scope, "key": key}
        token = uuid.uuid4().hex
        existing = None
        for _ in range(2):  # dono pode liberar entre o DuplicateKeyError e o find_one: repete o claim
            try:
                await self.col.insert_one(
                    {**ident, "body_hash": body_hash, "status_code": None, "response": None, "created_at": now(),
                     "token": token}
                )  # fmt: skip
                return None, token
            except DuplicateKeyError:
                # Claim órfão (processo morreu antes de completar/liberar): quem vence esta atualização
                # condicional assume a execução; os demais veem "em andamento".
                took = await self.col.find_one_and_update(
                    {**ident, "status_code": None, "created_at": {"$lte": now() - timedelta(seconds=STALE_S)}},
                    {"$set": {"body_hash": body_hash, "created_at": now(), "token": token}},
                )
                if took is not None:
                    return None, token
                existing = await self.col.find_one(ident)
                if existing is not None:
                    break
        return existing, ""

    async def complete(
        self, customer_id: str, scope: str, key: str, token: str, status_code: int, response: dict
    ) -> None:
        await self.col.update_one(
            {"customer_id": customer_id, "scope": scope, "key": key, "token": token, "status_code": None},
            {"$set": {"status_code": status_code, "response": response}},
        )

    async def release(self, customer_id: str, scope: str, key: str, token: str) -> None:
        """Libera a chave de uma execução que falhou (erro, 504): repetir reexecuta."""
        await self.col.delete_one(
            {"customer_id": customer_id, "scope": scope, "key": key, "token": token, "status_code": None}
        )

    async def purge(self, customer_id: str) -> None:
        """Respostas guardadas trazem o pedido (com endereço): somem junto com a conta."""
        await self.col.delete_many({"customer_id": customer_id})
