from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError


class EmailTaken(Exception):
    pass


class UserRepo:
    def __init__(self, db: AsyncDatabase):
        self.col = db["users"]

    async def create(self, doc: dict) -> dict:
        try:
            await self.col.insert_one(doc)
        except DuplicateKeyError as exc:
            raise EmailTaken from exc
        return doc

    async def get(self, user_id: str) -> dict | None:
        return await self.col.find_one({"_id": user_id})

    async def get_by_email(self, email: str) -> dict | None:
        return await self.col.find_one({"email": email})

    async def promote_to_admin(self, user_id: str) -> None:
        await self.col.update_one({"_id": user_id}, {"$set": {"role": "admin"}})

    async def bump_token_version(self, user_id: str) -> None:
        """Invalida todos os tokens já emitidos para o usuário (logout/revogação)."""
        await self.col.update_one({"_id": user_id}, {"$inc": {"token_version": 1}})

    async def count(self) -> int:
        return await self.col.count_documents({})
