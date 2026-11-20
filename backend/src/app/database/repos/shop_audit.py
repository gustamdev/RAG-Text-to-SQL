import uuid
from datetime import timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now


class ShopAuditRepo:
    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_audit"]

    async def add(
        self, event: str, actor: str, ip_hmac: str | None, meta: dict | None = None, ttl_days: int = 90
    ) -> None:
        """Só pseudônimos (HMAC) e metadados sem dado pessoal. `ip_hmac` só nos eventos de risco.
        TTL por documento (`expires_at`): 90 dias por padrão; eventos admin_view_* usam mais."""
        t = now()
        await self.col.insert_one(
            {
                "_id": uuid.uuid4().hex,
                "event": event,
                "actor": actor,
                "ip_hmac": ip_hmac,
                "meta": meta or {},
                "created_at": t,
                "expires_at": t + timedelta(days=ttl_days),
            }
        )
