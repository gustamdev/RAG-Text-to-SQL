import uuid

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now


class ShopAddressRepo:
    """Toda query filtra por customer_id: endereço alheio é indistinguível de inexistente."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_addresses"]

    async def for_customer(self, customer_id: str) -> list[dict]:
        return await self.col.find({"customer_id": customer_id}).sort("created_at", ASCENDING).to_list(100)

    async def get(self, customer_id: str, address_id: str) -> dict | None:
        return await self.col.find_one({"_id": address_id, "customer_id": customer_id})

    async def count(self, customer_id: str) -> int:
        return await self.col.count_documents({"customer_id": customer_id})

    async def insert(self, customer_id: str, fields: dict) -> dict:
        doc = {"_id": uuid.uuid4().hex, "customer_id": customer_id, **fields, "created_at": now(), "updated_at": now()}
        await self.col.insert_one(doc)
        return doc

    async def update(self, customer_id: str, address_id: str, fields: dict) -> dict | None:
        result = await self.col.update_one(
            {"_id": address_id, "customer_id": customer_id}, {"$set": {**fields, "updated_at": now()}}
        )
        return await self.get(customer_id, address_id) if result.matched_count else None

    async def unset_default_except(self, customer_id: str, keep_id: str) -> None:
        await self.col.update_many(
            {"customer_id": customer_id, "_id": {"$ne": keep_id}}, {"$set": {"is_default": False}}
        )

    async def delete(self, customer_id: str, address_id: str) -> bool:
        return (await self.col.delete_one({"_id": address_id, "customer_id": customer_id})).deleted_count == 1
