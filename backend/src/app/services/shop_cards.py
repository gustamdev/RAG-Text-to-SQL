"""Cartões salvos do cliente (máx. MAX_CARDS), pagamento SIMULADO. Nunca grava PAN, CVV nem titular.

shortcut: `outcome` (resultado simulado fixado no cadastro: TEST_CARDS.get(pan) ou "refused") faz o papel do
token do cofre; com gateway real, trocar por token do provedor e apagar `outcome`.
"""

import logging
from datetime import date

from pymongo.errors import DuplicateKeyError

from app.core.errors import Conflict, NotFound, UnprocessableEntity
from app.database.repos.shop_audit import ShopAuditRepo
from app.database.repos.shop_cards import ShopCardRepo
from app.schemas.shop_cards import CardIn, CardOut
from app.services import payment_gateway
from app.services.shop_auth_service import pseudo

logger = logging.getLogger(__name__)

MAX_CARDS = 3
LIMIT = f"Limite de {MAX_CARDS} cartões atingido."
NOT_FOUND = "Cartão não encontrado."
EXPIRED = "Cartão vencido."


def out(doc: dict) -> CardOut:
    return CardOut(id=doc["_id"], **{k: doc[k] for k in CardOut.model_fields if k != "id"})


class ShopCards:
    def __init__(self, db):
        self.repo, self.audit = ShopCardRepo(db), ShopAuditRepo(db)

    async def _audit(self, event: str, customer_id: str, card_id: str) -> None:
        try:  # só ids: nada do cartão
            await self.audit.add(event, pseudo(customer_id), None, {"card_id": card_id})
        except Exception:  # noqa: BLE001 - auditoria não derruba a operação
            logger.exception("Falha ao gravar auditoria (%s).", event)

    async def all(self, customer_id: str) -> list[CardOut]:
        return [out(d) for d in await self.repo.for_customer(customer_id)]

    async def get(self, customer_id: str, card_id: str) -> dict:
        doc = await self.repo.get(customer_id, card_id)
        if doc is None:
            raise NotFound(NOT_FOUND)
        return doc

    async def add(self, customer_id: str, card: CardIn) -> tuple[CardOut, bool]:
        """422 (Luhn/vencido) antes de qualquer escrita; 409 no limite. Devolve (cartão, criado).
        Mesmo cartão: devolve o existente (criado=False), com a validade atualizada se mudou."""
        pan = card.card_number.get_secret_value()
        if pan not in payment_gateway.TEST_CARDS and not payment_gateway.luhn_ok(pan):
            raise payment_gateway.InvalidCard
        today = date.today()
        if (card.exp_year, card.exp_month) < (today.year, today.month):
            raise UnprocessableEntity(EXPIRED)
        fingerprint = pseudo(f"pan:{customer_id}:{pan}")  # HMAC com escopo do cliente: sem correlação entre contas
        if existing := await self.repo.by_fingerprint(customer_id, fingerprint):
            if (existing["exp_month"], existing["exp_year"]) != (card.exp_month, card.exp_year):
                existing = (
                    await self.repo.set_expiry(customer_id, existing["_id"], card.exp_month, card.exp_year) or existing
                )
            return out(existing), False
        if await self.repo.count(customer_id) >= MAX_CARDS:
            raise Conflict(LIMIT)
        fields = {
            "brand": payment_gateway.brand_of(pan), "last4": pan[-4:], "exp_month": card.exp_month,
            "exp_year": card.exp_year, "fingerprint": fingerprint,
            "outcome": payment_gateway.TEST_CARDS.get(pan, "refused"),
        }  # fmt: skip
        try:
            doc = await self.repo.insert(customer_id, fields)
        except DuplicateKeyError:  # corrida do mesmo cartão: vale o que já está salvo
            return out(await self.repo.by_fingerprint(customer_id, fingerprint)), False  # type: ignore[arg-type]
        if await self.repo.count(customer_id) > MAX_CARDS:  # corrida: recontou e passou, desfaz
            await self.repo.delete(customer_id, doc["_id"])
            raise Conflict(LIMIT)
        await self._audit("card_added", customer_id, doc["_id"])
        return out(doc), True

    async def delete(self, customer_id: str, card_id: str) -> None:
        if not await self.repo.delete(customer_id, card_id):
            raise NotFound(NOT_FOUND)
        await self._audit("card_removed", customer_id, card_id)
