"""Contrato de checkout, pagamento simulado e pedidos. Ver docs/api-loja.md (seção 6)."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.schemas.shop_store import Strict


class CheckoutIn(Strict):
    address_id: Annotated[str, Field(min_length=1, max_length=64)]
    shipping_option: Literal["standard", "economy"]


class PayIn(Strict):
    # SecretStr: repr/log mascarados. O corpo nunca é gravado; só bandeira + últimos 4 saem daqui.
    card_number: SecretStr = Field(repr=False)
    holder: SecretStr = Field(min_length=1, max_length=60, repr=False)
    exp_month: Annotated[int, Field(ge=1, le=12)]
    exp_year: Annotated[int, Field(ge=2000, le=2100)]
    cvv: SecretStr = Field(repr=False)

    @field_validator("card_number", mode="before")
    @classmethod
    def _pan(cls, value):
        """Aceita espaço/hífen entre grupos; 13 a 19 dígitos."""
        digits = value.replace(" ", "").replace("-", "") if isinstance(value, str) else value
        if not isinstance(digits, str) or not re.fullmatch(r"\d{13,19}", digits):
            raise ValueError("Número de cartão inválido.")  # sem ecoar o valor
        return digits

    @field_validator("cvv", mode="before")
    @classmethod
    def _cvv(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{3,4}", value):
            raise ValueError("CVV inválido.")
        return value


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


class PayOut(BaseModel):
    order: OrderOut
    payment: PaymentInfo


class OrderSummary(BaseModel):
    order_id: str
    state: str
    total_cents: int
    item_count: int
    created_at: str


class OrdersPage(BaseModel):
    items: list[OrderSummary]
    total: int
    page: int
    page_size: int
