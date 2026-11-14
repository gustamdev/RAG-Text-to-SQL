import uuid

from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now


class ShopAuditRepo:
    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_audit"]

    async def add(self, event: str, actor: str, ip_hmac: str | None, meta: dict | None = None) -> None:
        """Só pseudônimos (HMAC) e metadados sem dado pessoal. `ip_hmac` só nos eventos de risco. TTL de 90 dias."""
        await self.col.insert_one(
            {
                "_id": uuid.uuid4().hex,
                "event": event,
                "actor": actor,
                "ip_hmac": ip_hmac,
                "meta": meta or {},
                "created_at": now(),
            }
        )
