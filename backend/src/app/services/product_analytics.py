"""Vitrine e backoffice de produtos: roda o SQL fixo de `database/analytics.py` e mapeia para schemas.

Sem LLM e sem validação de SQL: as consultas são constantes do código (ver analytics.py).
"""

import asyncio
from typing import Any

from app.core.errors import NotFound, ServiceUnavailable
from app.database import analytics
from app.database.sql_engine import EngineUnavailable, QueryTimeout, SQLEngine
from app.schemas.product import (
    AdminCategoryRow,
    AdminProductDetail,
    AdminProductPage,
    AdminProductRow,
    AdminSort,
    CategoryOut,
    Kpis,
    MonthlyPoint,
    Overview,
    ProductDetail,
    ProductPage,
    ProductSummary,
    PublicSort,
    RatingBucket,
    SortOrder,
    TopSeller,
)

PRODUCT_NOT_FOUND = "Produto não encontrado."
# Teto de linhas lidas por consulta: maior que qualquer página (100), categorias (~75) e meses (~25).
MAX_ROWS = 5000
RATING_SCORES = (1, 2, 3, 4, 5)


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _money(value: float | None) -> float:
    return round(float(value or 0), 2)


def make_label(category: str, category_en: str, product_id: str) -> str:
    """Rótulo sintético: o Olist não tem nome de produto."""
    return f"{category_en or category} · #{product_id[:8]}"


def _summary_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "product_id": row["product_id"],
        "label": make_label(row["category"], row["category_en"], row["product_id"]),
        "category": row["category"],
        "category_en": row["category_en"],
        "avg_price": _money(row["avg_price"]),
        "avg_rating": _round(row["avg_rating"]),
        "review_count": int(row["review_count"]),
        "units_sold": int(row["units_sold"]),
        "photos_qty": row["photos_qty"],
    }


def _admin_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **_summary_fields(row),
        "revenue": _money(row["revenue"]),
        "freight_avg": _money(row["freight_avg"]),
        "bad_review_pct": _round(row["bad_review_pct"]),
        "late_pct": _round(row["late_pct"]),
        "sellers": int(row["sellers"]),
        "rank": int(row["revenue_rank"]),
    }


def _dimensions(row: dict[str, Any]) -> dict[str, Any]:
    keys = ("weight_g", "length_cm", "height_cm", "width_cm", "name_length", "description_length")
    return {key: row[key] for key in keys}


def _category_row(row: dict[str, Any]) -> AdminCategoryRow:
    return AdminCategoryRow(
        category=row["category"],
        category_en=row["category_en"],
        products=int(row["products"]),
        units_sold=int(row["units_sold"]),
        revenue=_money(row["revenue"]),
        avg_price=_money(row["avg_price"]),
        avg_rating=_round(row["avg_rating"]),
        bad_review_pct=_round(row["bad_review_pct"]),
        late_pct=_round(row["late_pct"]),
        rank=int(row["revenue_rank"]),
    )


def _monthly_point(row: dict[str, Any]) -> MonthlyPoint:
    return MonthlyPoint(
        month=row["month"], revenue=_money(row["revenue"]), units=int(row["units"]), orders=int(row["orders"])
    )


class ProductAnalytics:
    def __init__(self, engine: SQLEngine):
        self.engine = engine

    async def _rows(self, query: analytics.Query, max_rows: int = MAX_ROWS) -> list[dict[str, Any]]:
        try:
            columns, rows, _ = await self.engine.run(query.sql, max_rows, query.params)
        except EngineUnavailable as exc:
            raise ServiceUnavailable("Motor de consultas indisponível no momento.") from exc
        except QueryTimeout as exc:
            raise ServiceUnavailable("A consulta demorou demais. Tente de novo em instantes.") from exc
        return [dict(zip(columns, row, strict=True)) for row in rows]

    async def _total(self, rows: list[dict[str, Any]], page: int, count_query: analytics.Query) -> int:
        if rows:
            return int(rows[0]["total_rows"])
        if page == 1:
            return 0
        # Página além do fim: a janela COUNT(*) OVER () não tem linha para devolver o total.
        counted = await self._rows(count_query, 1)
        return int(counted[0]["total_rows"]) if counted else 0

    # --- Vitrine pública ---------------------------------------------------------------

    async def list_products(
        self, q: str | None, category: str | None, sort: PublicSort, page: int, page_size: int
    ) -> ProductPage:
        rows = await self._rows(analytics.public_products_page(q, category, sort, page, page_size), page_size)
        total = await self._total(rows, page, analytics.public_products_count(q, category))
        items = [ProductSummary(**_summary_fields(row)) for row in rows]
        return ProductPage(items=items, total=total, page=page, page_size=page_size)

    async def get_product(self, product_id: str) -> ProductDetail:
        rows = await self._rows(analytics.product_summary(product_id), 1)
        if not rows:
            raise NotFound(PRODUCT_NOT_FOUND)
        row = rows[0]
        related = await self._rows(analytics.related_products(product_id, row["category"]), analytics.MAX_RELATED)
        return ProductDetail(
            **_summary_fields(row),
            **_dimensions(row),
            related=[ProductSummary(**_summary_fields(r)) for r in related],
        )

    async def categories(self) -> list[CategoryOut]:
        rows = await self._rows(analytics.public_categories())
        return [
            CategoryOut(
                category=r["category"],
                category_en=r["category_en"],
                products=int(r["products"]),
                units_sold=int(r["units_sold"]),
            )
            for r in rows
        ]

    # --- Backoffice --------------------------------------------------------------------

    async def admin_products(
        self,
        q: str | None,
        category: str | None,
        min_rating: float | None,
        sort: AdminSort,
        order: SortOrder,
        page: int,
        page_size: int,
    ) -> AdminProductPage:
        query = analytics.admin_products_page(q, category, min_rating, sort, order, page, page_size)
        rows = await self._rows(query, page_size)
        total = await self._total(rows, page, analytics.admin_products_count(q, category, min_rating))
        items = [AdminProductRow(**_admin_fields(row)) for row in rows]
        return AdminProductPage(items=items, total=total, page=page, page_size=page_size)

    async def admin_product(self, product_id: str) -> AdminProductDetail:
        rows = await self._rows(analytics.admin_product(product_id), 1)
        if not rows:
            raise NotFound(PRODUCT_NOT_FOUND)
        row = rows[0]
        monthly, distribution, sellers = await asyncio.gather(
            self._rows(analytics.product_monthly(product_id)),
            self._rows(analytics.product_rating_distribution(product_id)),
            self._rows(analytics.product_top_sellers(product_id), analytics.MAX_TOP_SELLERS),
        )
        counts = {int(r["score"]): int(r["total"]) for r in distribution}
        return AdminProductDetail(
            **_admin_fields(row),
            **_dimensions(row),
            rating_distribution=[RatingBucket(score=s, count=counts.get(s, 0)) for s in RATING_SCORES],
            monthly=[_monthly_point(r) for r in monthly],
            top_sellers=[
                TopSeller(
                    seller_id=r["seller_id"],
                    seller_state=r["seller_state"],
                    units=int(r["units"]),
                    revenue=_money(r["revenue"]),
                )
                for r in sellers
            ],
        )

    async def admin_categories(self) -> list[AdminCategoryRow]:
        return [_category_row(r) for r in await self._rows(analytics.admin_categories())]

    async def overview(self) -> Overview:
        kpis, monthly, categories, products = await asyncio.gather(
            self._rows(analytics.overview_kpis(), 1),
            self._rows(analytics.overview_monthly()),
            self._rows(analytics.admin_categories(analytics.OVERVIEW_TOP_N), analytics.OVERVIEW_TOP_N),
            self._rows(analytics.top_products(analytics.OVERVIEW_TOP_N), analytics.OVERVIEW_TOP_N),
        )
        k = kpis[0]
        return Overview(
            kpis=Kpis(
                revenue=_money(k["revenue"]),
                units=int(k["units"]),
                orders=int(k["orders"]),
                avg_ticket=_money(k["avg_ticket"]),
                avg_rating=_round(k["avg_rating"]),
                late_pct=_round(k["late_pct"]),
                products=int(k["products"]),
                sellers=int(k["sellers"]),
                categories=int(k["categories"]),
            ),
            monthly=[_monthly_point(r) for r in monthly],
            top_categories=[_category_row(r) for r in categories],
            top_products=[AdminProductRow(**_admin_fields(r)) for r in products],
        )
