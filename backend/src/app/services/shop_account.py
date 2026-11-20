"""Conta do cliente e direitos do titular (LGPD): exportar, corrigir e excluir (anonimizar)."""

import logging
from collections.abc import Callable
from datetime import datetime

from pymongo.asynchronous.database import AsyncDatabase

from app.api.shop_deps import SnapshotRefresher
from app.auth.security import hash_password, verify_password
from app.config import settings
from app.core.errors import NotFound, TooManyRequests, Unauthorized, UnprocessableEntity
from app.core.timeutil import iso, now
from app.database.repos.shop_addresses import ShopAddressRepo
from app.database.repos.shop_audit import ShopAuditRepo
from app.database.repos.shop_cards import ShopCardRepo
from app.database.repos.shop_carts import ShopCartRepo
from app.database.repos.shop_customers import ShopCustomerRepo
from app.database.repos.shop_flags import ShopFlagRepo
from app.database.repos.shop_idempotency import ShopIdempotencyRepo
from app.database.repos.shop_orders import EXPORT_LIMIT, ShopOrderRepo
from app.database.repos.shop_otp import ShopOtpRepo
from app.database.repos.shop_payments import ShopPaymentRepo
from app.schemas.shop_account import ChangePasswordIn, DeleteAccountIn, ProfileOut, ProfilePatch
from app.services.shop_auth_service import _argon, _notify_password_changed, pseudo
from app.services.shop_checkout import ShopCheckout
from app.services.shop_legal import art19_declaration

logger = logging.getLogger(__name__)
WRONG_PASSWORD = "Senha incorreta."
WRONG_CURRENT = "Senha atual incorreta."
SAME_PASSWORD = "A nova senha deve ser diferente da atual."
TOO_MANY = "Muitas tentativas. Aguarde alguns minutos e tente de novo."
DELETE_MAX_FAILURES = 5
SNAPSHOT_PENDING = "snapshot_refresh"  # marcador em shop_flags: refresh do agente a repetir
_ORDER_FIELDS = (
    "order_id", "state", "items", "subtotal_cents", "freight_cents", "discount_cents", "total_cents",
    "shipping", "address", "created_at",
)  # fmt: skip
_PAYMENT_FIELDS = ("order_id", "status", "brand", "last4", "amount_cents", "created_at")
_CARD_FIELDS = ("id", "brand", "last4", "exp_month", "exp_year", "created_at")
_PROFILE = ("nickname", "phone", "terms_version", "terms_accepted_at", "created_at", "last_login_at")


def _jsonable(value):
    """Datas viram ISO; resto passa. Recursivo (pedidos têm timeline e itens)."""
    if hasattr(value, "isoformat"):
        return iso(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _pick(doc: dict, fields: tuple[str, ...]) -> dict:
    return {k: doc[k] for k in fields if k in doc}


class ShopAccount:
    def __init__(self, db: AsyncDatabase, refresher: SnapshotRefresher):
        self.customers = ShopCustomerRepo(db)
        self.addresses = ShopAddressRepo(db)
        self.cards = ShopCardRepo(db)
        self.orders = ShopOrderRepo(db)
        self.payments = ShopPaymentRepo(db)
        self.carts = ShopCartRepo(db)
        self.idem = ShopIdempotencyRepo(db)
        self.audit = ShopAuditRepo(db)
        self.otp = ShopOtpRepo(db)
        self.flags = ShopFlagRepo(db)
        self.checkout = ShopCheckout(db, refresher)
        self.refresher = refresher

    async def _load(self, customer_id: str) -> dict:
        doc = await self.customers.get(customer_id)
        if doc is None or doc.get("deleted_at"):
            raise NotFound("Conta não encontrada.")
        return doc

    async def export(self, customer_id: str) -> dict:
        """Só dados do próprio titular (todas as queries filtram por customer_id). Nunca hash de senha."""
        customer = await self._load(customer_id)
        cart = await self.carts.get(customer_id)
        rows = await self.addresses.for_customer(customer_id)
        addresses = [{k: v for k, v in a.items() if k != "customer_id"} for a in rows]
        orders = await self.orders.all_for(customer_id)
        payments = await self.payments.all_for(customer_id)
        truncated = {"orders": len(orders) >= EXPORT_LIMIT, "payments": len(payments) >= EXPORT_LIMIT}
        data = {
            "customer": {"id": customer_id, "email": customer["email"], **{k: customer.get(k) for k in _PROFILE}},
            "addresses": addresses,
            "cards": [_pick({**c, "id": c["_id"]}, _CARD_FIELDS) for c in await self.cards.for_customer(customer_id)],
            "orders": [_pick(o, _ORDER_FIELDS) for o in orders],
            "payments": [_pick(p, _PAYMENT_FIELDS) for p in payments],
            "cart": {"items": cart["items"]} if cart else None,
            "exported_at": now(),
            "art19": art19_declaration(),
            "truncated": truncated,
        }  # fmt: skip
        if any(truncated.values()):
            data["warning"] = (
                f"Exportação limitada a {EXPORT_LIMIT} itens por lista: há registros a mais. "
                "Peça a declaração completa ao encarregado."
            )
        await self.audit.add("dsar_export", pseudo(customer_id), None)
        return _jsonable(data)

    async def update(self, customer_id: str, body: ProfilePatch) -> ProfileOut:
        await self._load(customer_id)
        doc = await self.customers.update_profile(customer_id, body.model_dump(exclude_unset=True))
        await self.audit.add("profile_updated", pseudo(customer_id), None)
        return ProfileOut(id=customer_id, nickname=doc.get("nickname"), email=doc["email"], phone=doc.get("phone"))

    async def _audit(self, event: str, customer_id: str) -> None:
        try:
            await self.audit.add(event, pseudo(customer_id), None)
        except Exception:  # noqa: BLE001 - auditoria não derruba a exclusão
            logger.exception("Falha ao gravar auditoria (%s).", event)

    async def _cleanup(self, customer_id: str, email: str) -> None:
        await self.checkout.cancel_open(customer_id)  # devolve o estoque reservado antes de anonimizar
        await self.orders.anonymize(customer_id)
        await self.payments.anonymize(customer_id)
        await self.addresses.delete_all(customer_id)
        await self.cards.delete_all(customer_id)
        await self.carts.clear(customer_id)
        await self.idem.purge(customer_id)
        await self.otp.delete_for_email(email)

    async def delete(self, customer_id: str, body: DeleteAccountIn) -> None:
        """Reautentica pela senha (5 tentativas por janela, contador persistido), anonimiza o cliente
        PRIMEIRO (revoga tokens, marca deleted_at) e só então limpa o resto; a limpeza pode ser repetida."""
        customer = await self.customers.get(customer_id)
        if customer is None:
            raise NotFound("Conta não encontrada.")
        email = customer["email"]
        if not customer.get("deleted_at"):
            key = pseudo(f"delete-pw:{customer_id}")
            if await self.otp.bump(key, "rate_delete_pw", settings.LOGIN_WINDOW_S) > DELETE_MAX_FAILURES:
                await self._audit("delete_fail", customer_id)
                raise TooManyRequests(TOO_MANY)
            if not await _argon(verify_password, body.password, customer.get("password_hash")):
                await self._audit("delete_fail", customer_id)
                raise Unauthorized(WRONG_PASSWORD)
            await self.otp.reset(key, "rate_delete_pw")
            await self.customers.anonymize(customer_id)  # antes da limpeza: o token morre e a conta não volta
        # else: retry de limpeza parcial (o cliente já está anonimizado; senha não existe mais).
        await self._finish(customer_id, email, "account_deleted")

    async def change_password(self, customer_id: str, body: ChangePasswordIn, spawn: Callable) -> None:
        """Reautentica pela senha atual (5 falhas por janela, contador persistido por cliente) e troca o hash;
        `set_password` incrementa token_version, então todas as sessões (inclusive esta) caem. Sem OTP."""
        customer = await self._load(customer_id)
        key = pseudo(f"change-pw:{customer_id}")
        if await self.otp.bump(key, "rate_change_pw", settings.LOGIN_WINDOW_S) > DELETE_MAX_FAILURES:
            await self._audit("password_change_fail", customer_id)
            raise TooManyRequests(TOO_MANY)
        if not await _argon(verify_password, body.current_password, customer.get("password_hash")):
            await self._audit("password_change_fail", customer_id)
            raise Unauthorized(WRONG_CURRENT)
        await self.otp.reset(key, "rate_change_pw")
        if body.new_password == body.current_password:
            raise UnprocessableEntity(SAME_PASSWORD)
        if not await self.customers.set_password(customer_id, await _argon(hash_password, body.new_password)):
            raise NotFound("Conta não encontrada.")
        await self._audit("password_changed", customer_id)
        spawn(_notify_password_changed, customer["email"])

    async def erase_inactive(self, customer: dict, inactive_before: datetime | None = None) -> bool:
        """Retenção: anonimiza conta inativa (sem senha; o titular não está presente) e limpa o resto.

        Com `inactive_before` a anonimização é condicional no banco; False = a conta voltou a ser ativa, nada feito."""
        if not await self.customers.anonymize(customer["_id"], inactive_before):
            return False
        await self._finish(customer["_id"], customer["email"], "account_retention_deleted")
        return True

    async def retry_cleanup(self, customer: dict) -> bool:
        """Conta já excluída (deleted_at) com endereço, carrinho ou pedido pendentes: repete a limpeza."""
        cid = customer["_id"]
        if not (
            await self.addresses.count(cid)
            or await self.cards.count(cid)
            or await self.carts.get(cid)
            or await self.orders.has_leftovers(cid)
        ):
            return False
        await self._finish(cid, customer["email"], "account_cleanup_retried")
        return True

    async def _finish(self, customer_id: str, email: str, event: str) -> None:
        await self._cleanup(customer_id, email)
        await self.idem.purge(customer_id)  # pedido em voo pode ter gravado idempotência durante a limpeza
        await self._audit(event, customer_id)
        try:
            await self.refresher.request()  # o agente deixa de ver o cliente
        except Exception:  # noqa: BLE001 - dados já apagados; o loop de expiração repete (shop_flags)
            logger.exception("Falha ao pedir refresh do snapshot após exclusão de conta.")
            await self.flags.set(SNAPSHOT_PENDING)
