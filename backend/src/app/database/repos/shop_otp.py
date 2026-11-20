"""OTPs e contadores de envio, todos em `shop_otp` (persistidos: sobrevivem a restart e a flood de chaves)."""

import hmac
import uuid
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.core.timeutil import now

WINDOW = timedelta(hours=1)  # o TTL do contador precisa durar a janela inteira
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class ShopOtpRepo:
    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_otp"]

    async def issue(self, email: str, purpose: str, code_hash: str, ttl_s: int) -> None:
        """Um documento por (email, purpose): gravar um novo OTP invalida o anterior e zera as tentativas."""
        t = now()
        doc = {
            "code_hash": code_hash,
            "attempts": 0,
            "ip_attempts": {},
            "created_at": t,
            "expires_at": t + timedelta(seconds=ttl_s),
        }
        for _ in range(2):  # upsert concorrente pode perder a corrida do índice único: tenta de novo
            try:
                await self.col.update_one(
                    {"email": email, "purpose": purpose},
                    {"$set": doc, "$setOnInsert": {"_id": uuid.uuid4().hex}},
                    upsert=True,
                )
                return
            except DuplicateKeyError:
                continue

    async def has(self, email: str, purpose: str) -> bool:
        """Há OTP VIVO (não expirado) para o par?"""
        flt = {"email": email, "purpose": purpose, "code_hash": {"$ne": None}, "expires_at": {"$gt": now()}}
        return await self.col.count_documents(flt) > 0

    async def consume(
        self, email: str, purpose: str, code_hash: str, max_total: int, max_per_ip: int, ip_key: str
    ) -> bool:
        """Conta a tentativa ANTES de comparar (atômico: chutes paralelos não furam o limite) e,
        se bater, apaga o documento (uso único; só uma requisição vence a corrida).

        Dois tetos: por IP-pseudônimo (`max_per_ip`: um IP estranho esgota só a própria cota) e o total
        (`max_total`, maior, contém quem troca de IP). O contador por IP vive no documento e zera a cada OTP novo."""
        ip_field = f"ip_attempts.{ip_key}"
        doc = await self.col.find_one_and_update(
            {
                "email": email,
                "purpose": purpose,
                "attempts": {"$lt": max_total},
                ip_field: {"$not": {"$gte": max_per_ip}},
                "expires_at": {"$gt": now()},
            },
            {"$inc": {"attempts": 1, ip_field: 1}},
            return_document=ReturnDocument.AFTER,
        )
        if doc is None or not doc.get("code_hash"):
            return False
        if not hmac.compare_digest(doc["code_hash"], code_hash):
            return False
        return (await self.col.delete_one({"_id": doc["_id"], "code_hash": doc["code_hash"]})).deleted_count == 1

    async def can_send(self, key: str, purpose: str, limit: int, cooldown_s: float) -> bool:
        """Só consulta (não consome): o limite de envio já estourou? Serve para responder 429 antes de olhar a senha."""
        t = now()
        blocked = {
            "email": key,
            "purpose": purpose,
            "expires_at": {"$gt": t},
            "$or": [{"sends": {"$gte": limit}}, {"last_sent_at": {"$gt": t - timedelta(seconds=cooldown_s)}}],
        }
        return await self.col.count_documents(blocked) == 0

    async def bump(self, key: str, purpose: str, window_s: float) -> int:
        """Contador de eventos por chave (HMAC) em janela FIXA que começa no 1º evento; $inc atômico.
        Devolve o total já contando este evento. Expira sozinho pelo TTL de `expires_at`."""
        t = now()
        flt = {"email": key, "purpose": purpose}
        fresh = {"created_at": t, "expires_at": t + timedelta(seconds=window_s)}
        # Janela vencida e o TTL do Mongo ainda não apagou: recomeça.
        await self.col.update_one({**flt, "expires_at": {"$lte": t}}, {"$set": {**fresh, "n": 0}})
        insert = {"_id": uuid.uuid4().hex, "code_hash": None, "attempts": 0, **fresh}
        for _ in range(3):  # upsert concorrente pode perder a corrida do índice único: tenta de novo
            try:
                doc = await self.col.find_one_and_update(
                    flt,
                    {"$inc": {"n": 1}, "$setOnInsert": insert},
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )
                return doc["n"]
            except DuplicateKeyError:
                continue
        raise RuntimeError("Contador indisponível.")

    async def reset(self, key: str, purpose: str) -> None:
        await self.col.delete_one({"email": key, "purpose": purpose})

    async def delete_for_email(self, email: str) -> None:
        """Apaga OTPs pendentes do e-mail (qualquer finalidade): somem junto com a conta."""
        await self.col.delete_many({"email": email})

    async def allow_send(self, key: str, purpose: str, limit: int, cooldown_s: float) -> bool:
        """Contador de envios por chave (HMAC de e-mail ou IP) em janela de 1 h + cooldown, via $inc atômico."""
        t = now()
        flt = {"email": key, "purpose": purpose}
        fresh = {"sends": 0, "last_sent_at": _EPOCH, "created_at": t, "expires_at": t + WINDOW}
        try:
            await self.col.update_one(
                flt, {"$setOnInsert": {"_id": uuid.uuid4().hex, "code_hash": None, "attempts": 0, **fresh}}, upsert=True
            )
        except DuplicateKeyError:
            pass  # outro request criou o contador agora: segue
        # Janela vencida e o TTL do Mongo ainda não apagou: recomeça.
        await self.col.update_one({**flt, "expires_at": {"$lte": t}}, {"$set": fresh})
        ok = await self.col.find_one_and_update(
            {**flt, "sends": {"$lt": limit}, "last_sent_at": {"$lte": t - timedelta(seconds=cooldown_s)}},
            {"$inc": {"sends": 1}, "$set": {"last_sent_at": t}},
        )
        return ok is not None
