"""Checkout, pagamento simulado e ciclo do pedido (E5).

Tudo é recalculado no servidor (carrinho, preço, frete, total). Sem transação (Mongo standalone):
- estoque: `find_one_and_update` condicional por item, com compensação se um item falhar;
- estado do pedido: só muda por `ShopOrderRepo.transition` (atualização condicional), então só um vence;
- idempotência: claim com índice único (customer_id, scope, key) ANTES de executar.
shortcut: se o processo morrer entre a transição e a devolução do estoque, a unidade fica presa; reconciliar
com um job que compare shop_orders ativos x estoque quando houver scheduler.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.api.shop_deps import SnapshotRefresher
from app.core.errors import Conflict, DomainError, NotFound
from app.core.timeutil import as_utc, iso, now
from app.database.repos.geolocation import GeolocationRepo
from app.database.repos.shop_addresses import ShopAddressRepo
from app.database.repos.shop_audit import ShopAuditRepo
from app.database.repos.shop_carts import ShopCartRepo
from app.database.repos.shop_idempotency import ShopIdempotencyRepo
from app.database.repos.shop_orders import ShopOrderRepo
from app.database.repos.shop_payments import ShopPaymentRepo, payment_id
from app.database.repos.shop_products import ShopProductRepo
from app.database.repos.shop_stock import ShopStockRepo
from app.schemas.shop_orders import (
    CheckoutIn,
    OrderOut,
    OrdersPage,
    OrderSummary,
    PayIn,
    PaymentInfo,
    PayOut,
)
from app.services import payment_gateway
from app.services.freight import FreightService
from app.services.shop_addresses import ShopAddresses
from app.services.shop_auth_service import pseudo
from app.services.shop_cart import ShopCart

logger = logging.getLogger(__name__)

RESERVATION = timedelta(minutes=15)
MAX_PAY_ATTEMPTS = 5
ACTIVE = ("created", "refused")  # estados que seguram reserva de estoque e aceitam pagar/cancelar
INVALID_TRANSITION = "Esta ação não é permitida para o estado atual do pedido."
EXPIRED = "Reserva expirada. Refaça o pedido."
NOT_FOUND = "Pedido não encontrado."
Response = tuple[int, dict]


class Unprocessable(DomainError):
    status_code = 422


class GatewayTimeout(DomainError):
    status_code = 504

    def __init__(self):
        super().__init__("Não conseguimos confirmar. Tente novamente.")


class InsufficientStock(Conflict):
    def __init__(self, items: list[dict]):
        super().__init__("Estoque insuficiente.")
        self.items = items


def body_hash(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def order_out(doc: dict) -> OrderOut:
    expires = doc.get("reservation_expires_at")
    return OrderOut(
        order_id=doc["order_id"], state=doc["state"], items=doc["items"],
        subtotal_cents=doc["subtotal_cents"], freight_cents=doc["freight_cents"],
        discount_cents=doc["discount_cents"], total_cents=doc["total_cents"],
        shipping=doc["shipping"], address=doc["address"], payment=doc.get("payment"),
        timeline=[{"state": t["state"], "at": iso(t["at"])} for t in doc["timeline"]],
        reservation_expires_at=iso(expires) if expires else None, created_at=iso(doc["created_at"]),
    )  # fmt: skip


class ShopCheckout:
    def __init__(self, db: AsyncDatabase, refresher: SnapshotRefresher | None = None):
        self.refresher = refresher or SnapshotRefresher()
        self.orders, self.payments = ShopOrderRepo(db), ShopPaymentRepo(db)
        self.idem, self.stock, self.audit = ShopIdempotencyRepo(db), ShopStockRepo(db), ShopAuditRepo(db)
        self.carts = ShopCartRepo(db)
        self.products = ShopProductRepo(db)
        self.cart = ShopCart(self.carts, self.products)
        self.addresses = ShopAddresses(ShopAddressRepo(db))
        self.freight = FreightService(GeolocationRepo(db))

    # --- infraestrutura ---------------------------------------------------------------------

    async def _audit(self, event: str, customer_id: str | None, ip: str, meta: dict) -> None:
        try:
            actor = pseudo(customer_id) if customer_id else "system"
            await self.audit.add(event, actor, pseudo(f"ip:{ip}") if ip else "system", meta)
        except Exception:  # noqa: BLE001 - auditoria não derruba a compra
            logger.exception("Falha ao gravar auditoria (%s).", event)

    async def _release(self, items: list[dict]) -> None:
        for item in items:
            await self.stock.release(item["product_id"], item["qty"])

    async def _idempotent(
        self, customer_id: str, scope: str, key: str, digest: str, run: Callable[[], Awaitable[Response]]
    ) -> Response:
        """Mesma chave e mesmo corpo: resposta original. Corpo diferente: 422. Erro (409, 504) libera a chave."""
        existing = await self.idem.claim(customer_id, scope, key, digest)
        if existing is not None:
            if existing["body_hash"] != digest:
                raise Unprocessable("Idempotency-Key já usada com outro conteúdo.")
            if existing["status_code"] is None:
                raise Conflict("Requisição em andamento. Tente novamente em instantes.")
            return existing["status_code"], existing["response"]
        try:
            status, response = await run()
        except BaseException:
            await self.idem.release(customer_id, scope, key)
            raise
        await self.idem.complete(customer_id, scope, key, status, response)
        return status, response

    # --- checkout ---------------------------------------------------------------------------

    async def checkout(self, customer_id: str, key: str, body: CheckoutIn, ip: str = "") -> Response:
        digest = body_hash(body.address_id, body.shipping_option)
        return await self._idempotent(customer_id, "checkout", key, digest, lambda: self._create(customer_id, body, ip))

    async def _create(self, customer_id: str, body: CheckoutIn, ip: str) -> Response:
        address = await self.addresses.get(customer_id, body.address_id)  # 404 uniforme se alheio
        cart = await self.cart.get(customer_id)
        if not cart.items:
            raise Conflict("Carrinho vazio.")
        if cart.blocked:
            raise Conflict("Revise os avisos do carrinho antes de finalizar.")
        weight = await self.cart.weight_g(customer_id) or 0
        options = await self.freight.options(address["zip"], weight, address.get("state"))
        option = next(o for o in options if o.code == body.shipping_option)

        items = [
            {
                "product_id": line.product_id, "title": line.title, "category": line.category, "qty": line.qty,
                "unit_price_cents": line.unit_price_cents, "line_total_cents": line.line_total_cents,
            }
            for line in cart.items
        ]  # fmt: skip
        reserved: list[dict] = []
        try:
            for item in items:
                if not await self.stock.reserve(item["product_id"], item["qty"]):
                    available = await self.products.get(item["product_id"])
                    raise InsufficientStock(
                        [{"product_id": item["product_id"], "available": max((available or {}).get("stock", 0), 0)}]
                    )
                reserved.append(item)
            created = now()
            subtotal = sum(i["line_total_cents"] for i in items)
            doc = {
                "order_id": uuid.uuid4().hex, "customer_id": customer_id, "state": "created", "items": items,
                "subtotal_cents": subtotal, "freight_cents": option.price_cents, "discount_cents": 0,
                "total_cents": subtotal + option.price_cents,
                "shipping": {
                    "option": option.code, "label": option.label, "days_min": option.days_min,
                    "days_max": option.days_max,
                },
                "address": {k: address.get(k) for k in (
                    "recipient", "zip", "street", "number", "complement", "district", "city", "state")},
                "payment_id": None, "payment": None, "timeline": [{"state": "created", "at": created}],
                "reservation_expires_at": created + RESERVATION, "created_at": created, "updated_at": created,
            }  # fmt: skip
            await self.orders.insert(doc)
        except BaseException:
            await self._release(reserved)  # compensação: devolve o que já foi reservado
            raise
        await self._audit("order_created", customer_id, ip, {"order_id": doc["order_id"]})
        return 201, order_out(doc).model_dump(mode="json")

    # --- pagamento --------------------------------------------------------------------------

    async def pay(self, customer_id: str, order_id: str, key: str, card: PayIn, ip: str = "") -> Response:
        digest = body_hash(order_id, card.card_number.get_secret_value()[-4:])  # nunca o PAN inteiro
        return await self._idempotent(
            customer_id, "pay", key, digest, lambda: self._pay(customer_id, order_id, card, ip)
        )

    async def _pay(self, customer_id: str, order_id: str, card: PayIn, ip: str) -> Response:
        order = await self.orders.get(customer_id, order_id)
        if order is None:
            raise NotFound(NOT_FOUND)
        if order["state"] not in ACTIVE:
            raise Conflict(INVALID_TRANSITION)
        if as_utc(order["reservation_expires_at"]) <= now():
            raise Conflict(EXPIRED)
        if await self.payments.attempts(order_id) >= MAX_PAY_ATTEMPTS:
            raise Conflict("Limite de tentativas de pagamento atingido.")

        # CVV e titular não passam do schema: o gateway só vê PAN e validade, e nada disso é gravado.
        result = await payment_gateway.charge(card.card_number.get_secret_value(), card.exp_month, card.exp_year)
        amount = order["total_cents"]
        if result.status == "timeout":
            await self.payments.record(order_id, customer_id, "timeout", result.brand, result.last4, amount)
            raise GatewayTimeout  # nada vai para shop_idempotency; a Order segue created
        info = PaymentInfo(status=result.status, brand=result.brand, last4=result.last4)
        approved = result.status == "approved"
        fields = {"payment": info.model_dump(), "payment_id": payment_id(order_id)}
        if approved:
            fields["reservation_expires_at"] = None
        updated = await self.orders.transition(
            order_id, "paid" if approved else "refused", from_states=ACTIVE, customer_id=customer_id,
            live_at=now(), set_fields=fields,
        )  # fmt: skip
        if updated is None:  # perdeu a corrida (outro pagamento, cancelamento ou expiração)
            raise Conflict(INVALID_TRANSITION)
        await self.payments.record(order_id, customer_id, result.status, result.brand, result.last4, amount)
        logger.info("Pagamento simulado order=%s status=%s", order_id, result.status)
        if approved:
            # A reserva já descontou o estoque: ao limpar a reserva, a baixa vira definitiva.
            await self.carts.clear(customer_id)
            await self._audit("order_paid", customer_id, ip, {"order_id": order_id})
            try:
                await self.refresher.request()
            except Exception:  # noqa: BLE001 - snapshot atrasado não desfaz a compra
                logger.exception("Falha ao pedir atualização do snapshot.")
        return 200, PayOut(order=order_out(updated), payment=info).model_dump(mode="json")

    # --- cancelar / expirar -----------------------------------------------------------------

    async def cancel(self, customer_id: str, order_id: str, ip: str = "") -> OrderOut:
        updated = await self.orders.transition(
            order_id, "canceled", from_states=ACTIVE, customer_id=customer_id,
            set_fields={"reservation_expires_at": None},
        )  # fmt: skip
        if updated is None:
            if await self.orders.get(customer_id, order_id) is None:
                raise NotFound(NOT_FOUND)
            raise Conflict(INVALID_TRANSITION)
        await self._release(updated["items"])  # só quem venceu a transição devolve o estoque
        await self._audit("order_canceled", customer_id, ip, {"order_id": order_id})
        return order_out(updated)

    async def expire_reservations(self, at: datetime | None = None) -> int:
        """Cancela created/refused com reserva vencida e devolve o estoque. Devolve quantos cancelou."""
        at = at or now()
        count = 0
        for order in await self.orders.expired(at):
            updated = await self.orders.transition(
                order["order_id"], "canceled", from_states=ACTIVE, expired_at=at,
                set_fields={"reservation_expires_at": None},
            )  # fmt: skip
            if updated is not None:
                await self._release(updated["items"])
                await self._audit("order_canceled", updated.get("customer_id"), "", {
                    "order_id": order["order_id"], "reason": "expired"})  # fmt: skip
                count += 1
        return count

    # --- leitura ----------------------------------------------------------------------------

    async def get(self, customer_id: str, order_id: str) -> OrderOut:
        doc = await self.orders.get(customer_id, order_id)
        if doc is None:
            raise NotFound(NOT_FOUND)
        return order_out(doc)

    async def list_orders(self, customer_id: str, page: int, page_size: int) -> OrdersPage:
        docs, total = await self.orders.page(customer_id, (page - 1) * page_size, page_size)
        items = [
            OrderSummary(
                order_id=d["order_id"], state=d["state"], total_cents=d["total_cents"],
                item_count=sum(i["qty"] for i in d["items"]), created_at=iso(d["created_at"]),
            )
            for d in docs
        ]  # fmt: skip
        return OrdersPage(items=items, total=total, page=page, page_size=page_size)
