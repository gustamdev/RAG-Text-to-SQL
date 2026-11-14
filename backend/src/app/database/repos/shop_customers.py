from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.timeutil import now
from app.database.repos.users import EmailTaken


class ShopCustomerRepo:
    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_customers"]

    async def create(self, doc: dict) -> dict:
        try:
            await self.col.insert_one(doc)
        except DuplicateKeyError as exc:
            raise EmailTaken from exc
        return doc

    async def get(self, customer_id: str) -> dict | None:
        return await self.col.find_one({"_id": customer_id})

    async def get_by_email(self, email: str) -> dict | None:
        return await self.col.find_one({"email": email})

    async def update_pending(self, email: str, fields: dict) -> None:
        """Recadastro de conta ainda não verificada: o último cadastro vale. Nunca toca em conta verificada."""
        await self.col.update_one({"email": email, "email_verified": False, "deleted_at": None}, {"$set": fields})

    async def mark_verified(self, customer_id: str) -> None:
        await self.col.update_one(
            {"_id": customer_id},
            {"$set": {"email_verified": True, "last_login_at": now()}, "$unset": {"pending_expires_at": ""}},
        )

    async def touch_login(self, customer_id: str) -> None:
        await self.col.update_one({"_id": customer_id}, {"$set": {"last_login_at": now()}})

    async def bump_token_version(self, customer_id: str) -> None:
        await self.col.update_one({"_id": customer_id}, {"$inc": {"token_version": 1}})
