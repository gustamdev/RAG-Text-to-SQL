from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.timeutil import now
from app.database.repos.shop_orders import EXPORT_LIMIT


class ShopPaymentRepo:
    """Um documento por pedido, atualizado a cada tentativa. Nunca recebe PAN, CVV nem titular: só bandeira e last4."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_payments"]

    async def reserve_attempt(self, order_id: str, limit: int) -> bool:
        """Conta a tentativa ANTES de cobrar (atômico): False se já gastou `limit`. Duas requisições
        paralelas não passam do teto."""
        for _ in range(2):  # upsert concorrente pode dar DuplicateKeyError sem o doc estar no teto: repete uma vez
            try:
                doc = await self.col.find_one_and_update(
                    {"order_id": order_id, "attempts": {"$lt": limit}},
                    {"$inc": {"attempts": 1}, "$setOnInsert": {"order_id": order_id, "created_at": now()}},
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
            except DuplicateKeyError:  # doc existe (índice único em order_id): se no teto, a 2ª volta também falha
                continue
            return doc is not None
        return False

    async def get(self, order_id: str) -> dict | None:
        return await self.col.find_one({"order_id": order_id}, {"_id": 0})

    async def record(
        self,
        order_id: str,
        customer_id: str,
        status: str,
        brand: str,
        last4: str,
        amount_cents: int,
        *,
        keep_approved: bool = False,
    ) -> dict:
        """`keep_approved`: não sobrescreve um pagamento já aprovado (o vencedor da corrida) e devolve o existente."""
        flt: dict = {"order_id": order_id}
        if keep_approved:
            flt["status"] = {"$ne": "approved"}  # com o doc aprovado, o upsert bate no índice único: nada é gravado
        try:
            doc = await self.col.find_one_and_update(
                flt,
                {
                    "$set": {
                        "payment_id": payment_id(order_id),
                        "customer_id": customer_id,
                        "status": status,
                        "brand": brand,
                        "last4": last4,
                        "amount_cents": amount_cents,
                        "updated_at": now(),
                    },
                    "$setOnInsert": {"order_id": order_id, "created_at": now()},
                },  # fmt: skip
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            if not keep_approved:
                raise
            return await self.get(order_id) or {}
        doc.pop("_id", None)
        return doc

    async def refund(self, order_id: str, customer_id: str, amount_cents: int) -> None:
        """Reembolso simulado de pedido pago e cancelado: `refund` no mesmo doc; o `status` original permanece."""
        at = now()
        await self.col.update_one(
            {"order_id": order_id},
            {
                "$set": {"refund": {"amount_cents": amount_cents, "at": at}, "updated_at": at},
                "$setOnInsert": {"order_id": order_id, "customer_id": customer_id, "created_at": at},
            },
            upsert=True,
        )

    async def all_for(self, customer_id: str) -> list[dict]:
        return await self.col.find({"customer_id": customer_id}, {"_id": 0}).to_list(EXPORT_LIMIT)

    async def delete_for_orders(self, order_ids: list[str]) -> None:
        await self.col.delete_many({"order_id": {"$in": order_ids}})

    async def anonymize(self, customer_id: str) -> None:
        await self.col.update_many({"customer_id": customer_id}, {"$set": {"brand": None, "last4": None}})


def payment_id(order_id: str) -> str:
    """Um pagamento por pedido: id derivado, estável entre tentativas."""
    return f"pay_{order_id}"
