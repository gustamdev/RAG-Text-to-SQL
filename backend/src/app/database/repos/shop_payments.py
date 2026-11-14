from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now


class ShopPaymentRepo:
    """Um documento por pedido, atualizado a cada tentativa. Nunca recebe PAN, CVV nem titular: só bandeira e last4."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_payments"]

    async def attempts(self, order_id: str) -> int:
        doc = await self.col.find_one({"order_id": order_id}, {"attempts": 1})
        return (doc or {}).get("attempts", 0)

    async def get(self, order_id: str) -> dict | None:
        return await self.col.find_one({"order_id": order_id}, {"_id": 0})

    async def record(
        self, order_id: str, customer_id: str, status: str, brand: str, last4: str, amount_cents: int
    ) -> dict:
        doc = await self.col.find_one_and_update(
            {"order_id": order_id},
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
                "$inc": {"attempts": 1},
            },  # fmt: skip
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        doc.pop("_id", None)
        return doc


def payment_id(order_id: str) -> str:
    """Um pagamento por pedido: id derivado, estável entre tentativas."""
    return f"pay_{order_id}"
