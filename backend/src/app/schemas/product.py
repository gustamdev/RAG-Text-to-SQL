"""Contrato da vitrine de produtos (público) e do backoffice (admin). O frontend depende destes nomes."""

from typing import Literal

from pydantic import BaseModel, Field

PublicSort = Literal["units", "rating", "price_asc", "price_desc"]
AdminSort = Literal["units", "revenue", "rating", "price", "bad_review_pct", "late_pct"]
SortOrder = Literal["asc", "desc"]

# Medidas físicas (float) e contagens de caracteres (int) do cadastro; qualquer uma pode faltar.
Measure = float | int | None


class ProductSummary(BaseModel):
    product_id: str
    # O Olist não tem nome nem imagem de produto: o rótulo é sintético (categoria + início do id).
    label: str
    category: str
    category_en: str
    avg_price: float
    # Nota média dos pedidos que contêm o produto (o Olist avalia o pedido, não o produto).
    avg_rating: float | None
    review_count: int
    units_sold: int
    photos_qty: int | None


class ProductPage(BaseModel):
    items: list[ProductSummary]
    total: int
    page: int
    page_size: int


class ProductDetail(ProductSummary):
    weight_g: Measure
    length_cm: Measure
    height_cm: Measure
    width_cm: Measure
    name_length: Measure
    description_length: Measure
    related: list[ProductSummary] = Field(default_factory=list, max_length=6)


class CategoryOut(BaseModel):
    category: str
    category_en: str
    products: int
    units_sold: int


class MonthlyPoint(BaseModel):
    month: str = Field(description="YYYY-MM")
    revenue: float
    units: int
    orders: int


class AdminProductRow(ProductSummary):
    revenue: float
    freight_avg: float
    bad_review_pct: float | None = Field(description="0-100: pedidos com nota <= 2 entre os avaliados.")
    late_pct: float | None = Field(description="0-100: pedidos entregues depois do prazo entre os entregues.")
    sellers: int
    rank: int = Field(description="Posição por receita entre todos os produtos.")


class AdminProductPage(BaseModel):
    items: list[AdminProductRow]
    total: int
    page: int
    page_size: int


class RatingBucket(BaseModel):
    score: int = Field(ge=1, le=5)
    count: int


class TopSeller(BaseModel):
    seller_id: str
    seller_state: str | None
    units: int
    revenue: float


class AdminProductDetail(AdminProductRow):
    weight_g: Measure
    length_cm: Measure
    height_cm: Measure
    width_cm: Measure
    name_length: Measure
    description_length: Measure
    rating_distribution: list[RatingBucket] = Field(description="Sempre 5 itens (notas 1 a 5).")
    monthly: list[MonthlyPoint]
    top_sellers: list[TopSeller] = Field(max_length=5)


class AdminCategoryRow(BaseModel):
    category: str
    category_en: str
    products: int
    units_sold: int
    revenue: float
    avg_price: float
    avg_rating: float | None
    bad_review_pct: float | None
    late_pct: float | None
    rank: int


class Kpis(BaseModel):
    revenue: float
    units: int
    orders: int
    avg_ticket: float
    avg_rating: float | None
    late_pct: float | None
    products: int
    sellers: int
    categories: int


class Overview(BaseModel):
    kpis: Kpis
    monthly: list[MonthlyPoint]
    top_categories: list[AdminCategoryRow]
    top_products: list[AdminProductRow]
