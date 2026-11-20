import uuid

from pymongo import ASCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now

ORDER = [("created_at", ASCENDING), ("_id", ASCENDING)]


class ShopCardRepo:
    """Cartões salvos (simulado): só bandeira, últimos 4, validade, fingerprint (HMAC) e o resultado simulado.
    Toda query filtra por customer_id: cartão alheio é indistinguível de inexistente."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_cards"]

    async def for_customer(self, customer_id: str) -> list[dict]:
        return await self.col.find({"customer_id": customer_id}).sort(ORDER).to_list(100)

    async def get(self, customer_id: str, card_id: str) -> dict | None:
        return await self.col.find_one({"_id": card_id, "customer_id": customer_id})

    async def by_fingerprint(self, customer_id: str, fingerprint: str) -> dict | None:
        return await self.col.find_one({"customer_id": customer_id, "fingerprint": fingerprint})

    async def count(self, customer_id: str) -> int:
        return await self.col.count_documents({"customer_id": customer_id})

    async def insert(self, customer_id: str, fields: dict) -> dict:
        doc = {"_id": uuid.uuid4().hex, "customer_id": customer_id, **fields, "created_at": now()}
        await self.col.insert_one(doc)
        return doc

    async def set_expiry(self, customer_id: str, card_id: str, exp_month: int, exp_year: int) -> dict:
        return await self.col.find_one_and_update(
            {"_id": card_id, "customer_id": customer_id},
            {"$set": {"exp_month": exp_month, "exp_year": exp_year}},
            return_document=ReturnDocument.AFTER,
        )

    async def delete(self, customer_id: str, card_id: str) -> bool:
        return (await self.col.delete_one({"_id": card_id, "customer_id": customer_id})).deleted_count == 1

    async def delete_all(self, customer_id: str) -> None:
        await self.col.delete_many({"customer_id": customer_id})
