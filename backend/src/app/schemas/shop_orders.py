"""Contrato de checkout, pagamento simulado e pedidos. Ver docs/api-loja.md (seção 6)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, model_validator

from app.schemas.shop_cards import CardIn
from app.schemas.shop_store import Strict


class CheckoutIn(Strict):
    address_id: Annotated[str, Field(min_length=1, max_length=64)]
    shipping_option: Literal["standard", "economy"]


class PayIn(CardIn):
    """Duas formas: cartão novo (campos do cartão + `save_card`) ou cartão salvo (`saved_card_id` + `cvv`).
    O CVV é validado só pelo formato e nunca gravado."""

    card_number: SecretStr | None = Field(default=None, repr=False)
    holder: SecretStr | None = Field(default=None, min_length=1, max_length=60, repr=False)
    exp_month: Annotated[int, Field(ge=1, le=12)] | None = None
    exp_year: Annotated[int, Field(ge=2000, le=2100)] | None = None
    saved_card_id: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    save_card: bool = False  # privacy by default: só salva com opt-in explícito; ignorado com `saved_card_id`

    @model_validator(mode="after")
    def _one_form(self) -> "PayIn":
        new = (self.card_number, self.holder, self.exp_month, self.exp_year)
        if self.saved_card_id is not None and any(v is not None for v in new):
            raise ValueError("Use um cartão salvo ou os dados de um cartão novo, não os dois.")
        if self.saved_card_id is None and any(v is None for v in new):
            raise ValueError("Informe os dados do cartão ou saved_card_id.")
        return self


class CancelIn(Strict):
    reason: Literal["changed_mind", "found_cheaper", "wrong_item", "delivery_too_long", "other"] = "other"


class OrderItemOut(BaseModel):
    product_id: str
    title: str
    category: str
    qty: int
    unit_price_cents: int
    line_total_cents: int


class ShippingOut(BaseModel):
    option: str
    label: str
    days_min: int
    days_max: int


class OrderAddressOut(BaseModel):
    recipient: str | None = None
    zip: str | None = None
    street: str | None = None
    number: str | None = None
    complement: str | None = None
    district: str | None = None
    city: str | None = None
    state: str | None = None


class PaymentInfo(BaseModel):
    status: Literal["approved", "refused", "timeout"]
    brand: str
    last4: str


class TimelineEntry(BaseModel):
    state: str
    at: str


class OrderOut(BaseModel):
    order_id: str
    state: str
    items: list[OrderItemOut]
    subtotal_cents: int
    freight_cents: int
    discount_cents: int
    total_cents: int
    shipping: ShippingOut
    address: OrderAddressOut
    payment: PaymentInfo | None
    timeline: list[TimelineEntry]
    reservation_expires_at: str | None
    created_at: str
    canceled_at: str | None = None
    cancel_reason: str | None = None
    refund_cents: int | None = None


class PayOut(BaseModel):
    order: OrderOut
    payment: PaymentInfo


class OrderSummary(BaseModel):
    order_id: str
    state: str
    total_cents: int
    item_count: int
    created_at: str
    canceled_at: str | None = None
    cancel_reason: str | None = None
    refund_cents: int | None = None


class OrdersPage(BaseModel):
    items: list[OrderSummary]
    total: int
    page: int
    page_size: int
