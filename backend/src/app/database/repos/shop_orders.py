from collections.abc import Iterable
from datetime import datetime

from pymongo import DESCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now

NO_ID = {"_id": 0}


class ShopOrderRepo:
    """Leituras do cliente filtram por customer_id (pedido alheio = inexistente). O estado só muda em `transition`."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_orders"]

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(dict(doc))

    async def get(self, customer_id: str, order_id: str) -> dict | None:
        return await self.col.find_one({"order_id": order_id, "customer_id": customer_id}, NO_ID)

    async def page(self, customer_id: str, skip: int, limit: int) -> tuple[list[dict], int]:
        flt = {"customer_id": customer_id}
        cursor = self.col.find(flt, NO_ID).sort([("created_at", DESCENDING)]).skip(skip).limit(limit)
        return await cursor.to_list(limit), await self.col.count_documents(flt)

    async def expired(self, at: datetime, limit: int = 500) -> list[dict]:
        flt = {"state": {"$in": ["created", "refused"]}, "reservation_expires_at": {"$lte": at}}
        return await self.col.find(flt, NO_ID).limit(limit).to_list(limit)

    async def transition(
        self,
        order_id: str,
        to_state: str,
        *,
        from_states: Iterable[str],
        customer_id: str | None = None,
        live_at: datetime | None = None,
        expired_at: datetime | None = None,
        set_fields: dict | None = None,
    ) -> dict | None:
        """Atualização condicional atômica: só vence quem encontra o pedido num `from_states`.

        `live_at`: exige reserva ainda válida. `expired_at`: exige reserva vencida. Devolve o documento novo ou None.
        """
        flt: dict = {"order_id": order_id, "state": {"$in": list(from_states)}}
        if customer_id is not None:
            flt["customer_id"] = customer_id
        if live_at is not None:
            flt["reservation_expires_at"] = {"$gt": live_at}
        if expired_at is not None:
            flt["reservation_expires_at"] = {"$lte": expired_at}
        at = now()
        # sem `projection`: mongomock devolve None com projeção + AFTER (o update é aplicado mesmo assim)
        doc = await self.col.find_one_and_update(
            flt,
            {
                "$set": {**(set_fields or {}), "state": to_state, "updated_at": at},
                "$push": {"timeline": {"state": to_state, "at": at}},
            },
            return_document=ReturnDocument.AFTER,
        )
        if doc is not None:
            doc.pop("_id", None)
        return doc
