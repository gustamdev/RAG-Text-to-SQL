"""Backoffice de produtos: métricas de receita, nota e entrega. Somente administradores."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import get_product_analytics, get_snapshot_service, require_admin
from app.schemas.product import (
    AdminCategoryRow,
    AdminProductDetail,
    AdminProductPage,
    AdminSort,
    Overview,
    SortOrder,
)
from app.schemas.snapshot import SnapshotStatus
from app.services.product_analytics import ProductAnalytics
from app.services.snapshot import SnapshotService

router = APIRouter(prefix="/admin", tags=["backoffice"], dependencies=[Depends(require_admin)])

ProductId = Annotated[str, Path(min_length=1, max_length=64)]


@router.get("/overview", response_model=Overview)
async def overview(service: ProductAnalytics = Depends(get_product_analytics)) -> Overview:
    return await service.overview()


@router.get("/products", response_model=AdminProductPage)
async def list_products(
    q: Annotated[str | None, Query(max_length=100, description="Prefixo do id ou trecho da categoria.")] = None,
    category: Annotated[str | None, Query(max_length=100)] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
    sort: AdminSort = "revenue",
    order: SortOrder = "desc",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
    service: ProductAnalytics = Depends(get_product_analytics),
) -> AdminProductPage:
    return await service.admin_products(q, category, min_rating, sort, order, page, page_size)


@router.get("/products/{product_id}", response_model=AdminProductDetail)
async def get_product(
    product_id: ProductId, service: ProductAnalytics = Depends(get_product_analytics)
) -> AdminProductDetail:
    return await service.admin_product(product_id)


@router.get("/categories", response_model=list[AdminCategoryRow])
async def list_categories(service: ProductAnalytics = Depends(get_product_analytics)) -> list[AdminCategoryRow]:
    return await service.admin_categories()


@router.get("/snapshot", response_model=SnapshotStatus)
async def snapshot_status(service: SnapshotService = Depends(get_snapshot_service)) -> SnapshotStatus:
    return SnapshotStatus(**service.status())


@router.post("/snapshot/refresh", response_model=SnapshotStatus)
async def refresh_snapshot(service: SnapshotService = Depends(get_snapshot_service)) -> SnapshotStatus:
    """Refresh manual: reconstrói o snapshot do agente agora (junta-se a um rebuild em andamento)."""
    return SnapshotStatus(**await service.refresh())
