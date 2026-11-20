"""Contrato da loja (catálogo, carrinho, endereços, frete). Dinheiro em centavos inteiros. Ver docs/api-loja.md."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

UFS = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


class Strict(BaseModel):
    """Corpo de entrada: campo desconhecido é 422 (mass assignment)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ProductId = Annotated[str, Field(min_length=1, max_length=64)]
Zip8 = Annotated[str, StringConstraints(pattern=r"^[0-9]{8}$")]
Text120 = Annotated[str, Field(max_length=120)]
UF = Annotated[str, StringConstraints(to_upper=True, pattern=r"^[A-Za-z]{2}$")]

# --- catálogo ---------------------------------------------------------------------------------

ShopSort = Literal["best_selling", "price_asc", "price_desc", "rating", "newest"]


class ProductCard(BaseModel):
    product_id: str
    title: str
    category: str
    category_label: str
    price_cents: int
    stock: int
    avg_rating: float | None
    review_count: int
    units_sold: int
    photos_qty: int
    image_url: str | None = None


class ProductDetail(ProductCard):
    weight_g: float | None
    length_cm: float | None
    height_cm: float | None
    width_cm: float | None
    rating_distribution: dict[str, int]


class ProductPage(BaseModel):
    items: list[ProductCard]
    total: int
    page: int
    page_size: int


class CategoryCount(BaseModel):
    category: str
    label: str
    product_count: int


class CategoryRef(BaseModel):
    category: str
    label: str


class Suggestions(BaseModel):
    products: list[ProductCard]
    categories: list[CategoryRef]


class BatchIn(Strict):
    ids: Annotated[list[ProductId], Field(min_length=1, max_length=50)]


class BatchOut(BaseModel):
    items: list[ProductCard]


# --- frete ------------------------------------------------------------------------------------


class FreightOption(BaseModel):
    code: Literal["standard", "economy"]
    label: str
    price_cents: int
    days_min: int
    days_max: int


class ZipOut(BaseModel):
    zip: str
    street: str | None = None
    district: str | None = None
    city: str
    state: str
    lat: float | None = None
    lng: float | None = None
    source: Literal["brasilapi", "viacep", "offline"]


class FreightOut(BaseModel):
    zip: str
    options: list[FreightOption]


class CartFreightIn(Strict):
    zip: Annotated[str, StringConstraints(pattern=r"^[0-9]{5}-?[0-9]{3}$")] | None = None
    address_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _exactly_one(self):
        if (self.zip is None) == (self.address_id is None):
            raise ValueError("Informe zip ou address_id (apenas um).")
        return self


# --- carrinho ---------------------------------------------------------------------------------


class CartAddIn(Strict):
    product_id: ProductId
    qty: Annotated[int, Field(ge=1, le=10)]


class CartPatchIn(Strict):
    qty: Annotated[int, Field(ge=1, le=10)] | None = None
    ack: bool | None = None

    @model_validator(mode="after")
    def _something(self):
        if self.qty is None and self.ack is None:
            raise ValueError("Informe qty e/ou ack.")
        return self


class CartMergeItem(Strict):
    product_id: ProductId
    qty: int


class CartMergeIn(Strict):
    items: Annotated[list[CartMergeItem], Field(max_length=50)]


class CartLine(BaseModel):
    product_id: str
    title: str
    category: str
    unit_price_cents: int
    qty: int
    line_total_cents: int
    stock: int
    warning: Literal["stock_reduced", "out_of_stock", "price_changed"] | None


class CartOut(BaseModel):
    items: list[CartLine]
    item_count: int
    subtotal_cents: int
    blocked: bool
    updated_at: str | None


# --- endereços --------------------------------------------------------------------------------


class AddressIn(Strict):
    label: Annotated[str, Field(min_length=1, max_length=30)]
    zip: Zip8
    city: Annotated[str, Field(min_length=1, max_length=120)]
    state: UF
    recipient: Text120 | None = None
    street: Text120 | None = None
    number: Annotated[str, Field(max_length=20)] | None = None
    complement: Text120 | None = None
    district: Text120 | None = None
    is_default: bool = False

    @model_validator(mode="after")
    def _uf(self):
        if self.state not in UFS:
            raise ValueError("UF inválida.")
        return self


class AddressPatch(Strict):
    """Subconjunto dos campos; os obrigatórios aceitam omissão, não null (o tipo não é Optional)."""

    label: Annotated[str, Field(min_length=1, max_length=30)] = None  # type: ignore[assignment]
    zip: Zip8 = None  # type: ignore[assignment]
    city: Annotated[str, Field(min_length=1, max_length=120)] = None  # type: ignore[assignment]
    state: UF = None  # type: ignore[assignment]
    recipient: Text120 | None = None
    street: Text120 | None = None
    number: Annotated[str, Field(max_length=20)] | None = None
    complement: Text120 | None = None
    district: Text120 | None = None
    is_default: bool = None  # type: ignore[assignment]

    @model_validator(mode="after")
    def _check(self):
        if not self.model_fields_set:
            raise ValueError("Nenhum campo para atualizar.")
        if "state" in self.model_fields_set and self.state not in UFS:
            raise ValueError("UF inválida.")
        return self


class AddressOut(BaseModel):
    id: str
    label: str
    recipient: str | None
    zip: str
    street: str | None
    number: str | None
    complement: str | None
    district: str | None
    city: str
    state: str
    is_default: bool
