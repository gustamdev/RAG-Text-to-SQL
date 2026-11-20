from datetime import datetime

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

    async def set_password(self, customer_id: str, password_hash: str) -> bool:
        """Troca o hash e revoga todos os JWT (token_version). Só conta verificada e não deletada."""
        res = await self.col.update_one(
            {"_id": customer_id, "email_verified": True, "deleted_at": None},
            {"$set": {"password_hash": password_hash}, "$inc": {"token_version": 1}},
        )
        return res.modified_count == 1

    async def update_profile(self, customer_id: str, fields: dict) -> dict | None:
        await self.col.update_one({"_id": customer_id}, {"$set": fields})
        return await self.get(customer_id)

    async def anonymize(self, customer_id: str, inactive_before: datetime | None = None) -> bool:
        """Apaga os dados pessoais mantendo o _id opaco (vínculo dos pedidos). E-mail vira placeholder único.

        Com `inactive_before`, só anonimiza se a conta ainda estiver inativa NO BANCO (quem logou desde a
        leitura do lote fica intacto). False = nada alterado."""
        flt: dict = {"_id": customer_id}
        if inactive_before is not None:
            flt |= {"deleted_at": None, **self._inactive_clause(inactive_before)}
        res = await self.col.update_one(
            flt,
            {
                "$set": {
                    "email": f"deleted-{customer_id}@anon.invalid",
                    "nickname": None,
                    "phone": None,
                    "password_hash": None,
                    "email_verified": False,
                    "deleted_at": now(),
                },
                "$inc": {"token_version": 1},
                "$unset": {"pending_expires_at": ""},
            },
        )
        return res.modified_count == 1

    @staticmethod
    def _inactive_clause(cutoff: datetime) -> dict:
        return {
            "email_verified": True,
            "$or": [{"last_login_at": {"$lt": cutoff}}, {"last_login_at": None, "created_at": {"$lt": cutoff}}],
        }

    async def inactive_before(self, cutoff: datetime, limit: int = 200) -> list[dict]:
        """Contas verificadas e ativas sem login desde `cutoff` (sem login nunca: vale created_at)."""
        flt = {"deleted_at": None, **self._inactive_clause(cutoff)}
        return await self.col.find(flt, {"password_hash": 0}).limit(limit).to_list(limit)

    async def unverified_before(self, cutoff: datetime, limit: int = 200) -> list[dict]:
        flt = {"email_verified": False, "deleted_at": None, "created_at": {"$lt": cutoff}}
        return await self.col.find(flt, {"email": 1}).limit(limit).to_list(limit)

    async def deleted_since(self, cutoff: datetime, after_id: str = "", limit: int = 500) -> list[dict]:
        """Contas anonimizadas ainda dentro da retenção (deleted_at >= cutoff), paginadas por _id."""
        flt = {"deleted_at": {"$gte": cutoff}, "_id": {"$gt": after_id}}
        return await self.col.find(flt, {"email": 1}).sort("_id", 1).limit(limit).to_list(limit)

    async def delete(self, customer_id: str) -> None:
        await self.col.delete_one({"_id": customer_id})

    async def purge_deleted_before(self, cutoff: datetime) -> int:
        return (await self.col.delete_many({"deleted_at": {"$lt": cutoff}})).deleted_count

    async def page(self, skip: int, limit: int) -> tuple[list[dict], int]:
        cursor = self.col.find({}, {"password_hash": 0}).sort([("created_at", -1)]).skip(skip).limit(limit)
        return await cursor.to_list(limit), await self.col.count_documents({})
