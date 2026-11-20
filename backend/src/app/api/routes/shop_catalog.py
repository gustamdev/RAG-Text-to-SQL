"""Catálogo público da loja. Rotas fixas (categories, suggest, batch) antes de `{product_id}`."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import enforce_catalog_rate_limit, get_app_db
from app.api.shop_params import ProductId, ZipQuery
from app.core.errors import NotFound
from app.database.repos.geolocation import GeolocationRepo
from app.database.repos.shop_products import ShopProductRepo
from app.schemas.shop_store import (
    BatchIn,
    BatchOut,
    CategoryCount,
    FreightOut,
    ProductDetail,
    ProductPage,
    ShopSort,
    Suggestions,
)
from app.services.freight import DEFAULT_WEIGHT_G, FreightService
from app.services.shop_catalog import NOT_FOUND, ShopCatalog, TtlCache

router = APIRouter(prefix="/shop/products", tags=["shop-catalog"], dependencies=[Depends(enforce_catalog_rate_limit)])


def get_catalog(request: Request, db: AsyncDatabase = Depends(get_app_db)) -> ShopCatalog:
    cache = getattr(request.app.state, "categories_cache", None)
    if cache is None:
        cache = request.app.state.categories_cache = TtlCache()
    return ShopCatalog(ShopProductRepo(db), cache)


@router.get("", response_model=ProductPage)
async def list_products(
    q: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    category: Annotated[str | None, Query(max_length=100)] = None,
    min_price_cents: Annotated[int | None, Query(ge=0, le=10**9)] = None,
    max_price_cents: Annotated[int | None, Query(ge=0, le=10**9)] = None,
    min_rating: Annotated[float | None, Query(ge=1, le=5)] = None,
    min_reviews: Annotated[int | None, Query(ge=1, le=10**9)] = None,
    in_stock: bool | None = None,
    sort: ShopSort = "best_selling",
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=48)] = 24,
    catalog: ShopCatalog = Depends(get_catalog),
) -> ProductPage:
    return await catalog.search(
        page, page_size, sort, q=q, category=category, min_price_cents=min_price_cents,
        max_price_cents=max_price_cents, min_rating=min_rating, min_reviews=min_reviews, in_stock=in_stock,
    )  # fmt: skip


@router.get("/categories", response_model=list[CategoryCount])
async def categories(catalog: ShopCatalog = Depends(get_catalog)) -> list[CategoryCount]:
    return await catalog.categories()


@router.get("/suggest", response_model=Suggestions)
async def suggest(
    q: Annotated[str, Query(min_length=2, max_length=80)], catalog: ShopCatalog = Depends(get_catalog)
) -> Suggestions:
    return await catalog.suggest(q)


@router.post("/batch", response_model=BatchOut)
async def batch(body: BatchIn, catalog: ShopCatalog = Depends(get_catalog)) -> BatchOut:
    return await catalog.batch(body.ids)


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: ProductId, catalog: ShopCatalog = Depends(get_catalog)) -> ProductDetail:
    return await catalog.detail(product_id)


@router.get("/{product_id}/freight", response_model=FreightOut)
async def product_freight(product_id: ProductId, zip: ZipQuery, db: AsyncDatabase = Depends(get_app_db)) -> FreightOut:
    product = await ShopProductRepo(db).get(product_id)
    if product is None:
        raise NotFound(NOT_FOUND)
    zip8 = zip.replace("-", "")
    options = await FreightService(GeolocationRepo(db)).options(zip8, product.get("weight_g") or DEFAULT_WEIGHT_G)
    return FreightOut(zip=zip8, options=options)
