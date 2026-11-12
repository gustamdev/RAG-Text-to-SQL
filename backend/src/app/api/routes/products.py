"""Vitrine pública de produtos Olist: leitura, sem login. Métricas internas ficam em /admin."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import enforce_public_rate_limit, get_product_analytics
from app.schemas.product import CategoryOut, ProductDetail, ProductPage, PublicSort
from app.services.product_analytics import ProductAnalytics

router = APIRouter(tags=["products"], dependencies=[Depends(enforce_public_rate_limit)])

ProductId = Annotated[str, Path(min_length=1, max_length=64)]


@router.get("/products", response_model=ProductPage)
async def list_products(
    q: Annotated[str | None, Query(max_length=100, description="Prefixo do id ou trecho da categoria.")] = None,
    category: Annotated[str | None, Query(max_length=100)] = None,
    sort: PublicSort = "units",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
    service: ProductAnalytics = Depends(get_product_analytics),
) -> ProductPage:
    return await service.list_products(q, category, sort, page, page_size)


@router.get("/products/{product_id}", response_model=ProductDetail)
async def get_product(
    product_id: ProductId, service: ProductAnalytics = Depends(get_product_analytics)
) -> ProductDetail:
    return await service.get_product(product_id)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(service: ProductAnalytics = Depends(get_product_analytics)) -> list[CategoryOut]:
    return await service.categories()
