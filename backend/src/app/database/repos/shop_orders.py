from collections.abc import Iterable
from datetime import datetime

from pymongo import DESCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.timeutil import now

NO_ID = {"_id": 0}
EXPORT_LIMIT = 10_000  # teto da exportação; acima disso a resposta avisa que truncou
OPEN_STATES = ["created", "refused"]


class ShopOrderRepo:
    """Leituras do cliente filtram por customer_id (pedido alheio = inexistente). O estado só muda em `transition`."""

    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_orders"]

    async def insert(self, doc: dict) -> None:
        await self.col.insert_one(dict(doc))

    async def delete(self, order_id: str) -> None:
        await self.col.delete_one({"order_id": order_id})

    async def get(self, customer_id: str, order_id: str) -> dict | None:
        return await self.col.find_one({"order_id": order_id, "customer_id": customer_id}, NO_ID)

    async def page(self, customer_id: str, skip: int, limit: int) -> tuple[list[dict], int]:
        flt = {"customer_id": customer_id}
        cursor = self.col.find(flt, NO_ID).sort([("created_at", DESCENDING)]).skip(skip).limit(limit)
        return await cursor.to_list(limit), await self.col.count_documents(flt)

    async def count_open(self, customer_id: str) -> int:
        return await self.col.count_documents({"customer_id": customer_id, "state": {"$in": ["created", "refused"]}})

    async def open_for(self, customer_id: str, limit: int = 100) -> list[dict]:
        flt = {"customer_id": customer_id, "state": {"$in": OPEN_STATES}}
        return await self.col.find(flt, NO_ID).limit(limit).to_list(limit)

    async def finished_before(self, cutoff: datetime, limit: int = 500) -> list[str]:
        """order_id de pedidos encerrados (não abertos) criados antes de `cutoff`: candidatos à retenção."""
        flt = {"state": {"$nin": OPEN_STATES}, "created_at": {"$lt": cutoff}}
        rows = await self.col.find(flt, {"order_id": 1, "_id": 0}).limit(limit).to_list(limit)
        return [r["order_id"] for r in rows]

    async def delete_many(self, order_ids: list[str]) -> None:
        await self.col.delete_many({"order_id": {"$in": order_ids}})

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

    async def all_for(self, customer_id: str) -> list[dict]:
        return (
            await self.col.find({"customer_id": customer_id}, NO_ID)
            .sort([("created_at", DESCENDING)])
            .to_list(EXPORT_LIMIT)
        )

    async def anonymize(self, customer_id: str) -> None:
        """Mantém itens e valores (contábil/estatística); apaga o endereço de entrega e brand/last4 do pagamento."""
        wipe = {
            f"address.{k}": None for k in ("recipient", "zip", "street", "number", "complement", "district", "city")
        }
        await self.col.update_many({"customer_id": customer_id}, {"$set": wipe})
        # `payment` é null em pedido sem pagamento: $set em campo de null falha no Mongo, então filtra por objeto
        await self.col.update_many(
            {"customer_id": customer_id, "payment": {"$type": "object"}},
            {"$set": {"payment.brand": None, "payment.last4": None}},
        )

    async def has_leftovers(self, customer_id: str) -> bool:
        """Pedido ainda aberto ou com endereço de entrega: a anonimização de uma conta excluída ficou pela metade."""
        flt = {"customer_id": customer_id, "$or": [{"address.zip": {"$ne": None}}, {"state": {"$in": OPEN_STATES}}]}
        return await self.col.count_documents(flt, limit=1) > 0

    async def admin_page(self, skip: int, limit: int) -> tuple[list[dict], int]:
        cursor = self.col.find({}, NO_ID).sort([("created_at", DESCENDING)]).skip(skip).limit(limit)
        return await cursor.to_list(limit), await self.col.count_documents({})
