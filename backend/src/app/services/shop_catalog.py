"""Catálogo da loja: leitura de `shop_products`. Nada aqui lê preço ou estoque do cliente."""

import time

from app.core.errors import NotFound
from app.database.repos.shop_products import ShopProductRepo, search_filter
from app.schemas.shop_store import (
    BatchOut,
    CategoryCount,
    CategoryRef,
    ProductCard,
    ProductDetail,
    ProductPage,
    Suggestions,
)
from app.services.blobstore import store

NOT_FOUND = "Produto não encontrado."
CATEGORIES_TTL_S = 60


class TtlCache:
    """Cache de 1 valor em processo (categorias mudam só no seed). Fica no app.state: um por processo."""

    def __init__(self, ttl_s: float = CATEGORIES_TTL_S):
        self.ttl_s, self._value, self._at = ttl_s, None, 0.0

    def get(self):
        return self._value if self._value is not None and time.monotonic() - self._at < self.ttl_s else None

    def set(self, value) -> None:
        self._value, self._at = value, time.monotonic()


def image_url(doc: dict) -> str | None:
    """`image_key` = "<container>/<blob>"; None se faltar o campo, a chave for inválida ou o arquivo não existir."""
    container, _, name = (doc.get("image_key") or "").partition("/")
    return store.url(container, name) if store.exists(container, name) else None


def card(doc: dict) -> ProductCard:
    rating = doc.get("avg_rating")
    return ProductCard(
        product_id=doc["product_id"],
        title=doc["title"],
        category=doc["category"],
        category_label=doc["category_label"],
        price_cents=doc["price_cents"],
        stock=max(doc["stock"], 0),
        avg_rating=None if rating is None else round(rating, 2),
        review_count=doc.get("review_count", 0),
        units_sold=doc.get("units_sold", 0),
        photos_qty=max(doc.get("photos_qty") or 0, 1),
        image_url=image_url(doc),
    )


class ShopCatalog:
    def __init__(self, products: ShopProductRepo, cache: TtlCache | None = None):
        self.products = products
        self.cache = cache or TtlCache()

    async def search(self, page: int, page_size: int, sort: str, **filters) -> ProductPage:
        docs, total = await self.products.search(search_filter(**filters), sort, (page - 1) * page_size, page_size)
        return ProductPage(items=[card(d) for d in docs], total=total, page=page, page_size=page_size)

    async def detail(self, product_id: str) -> ProductDetail:
        doc = await self.products.get(product_id)
        if doc is None:
            raise NotFound(NOT_FOUND)
        return ProductDetail(
            **card(doc).model_dump(),
            weight_g=doc.get("weight_g"),
            length_cm=doc.get("length_cm"),
            height_cm=doc.get("height_cm"),
            width_cm=doc.get("width_cm"),
            rating_distribution=doc.get("rating_distribution", {}),
        )

    async def categories(self) -> list[CategoryCount]:
        return [CategoryCount(**c) for c in await self._categories()]

    async def _categories(self) -> list[dict]:
        cached = self.cache.get()
        if cached is None:
            cached = await self.products.categories()
            self.cache.set(cached)
        return cached

    async def batch(self, ids: list[str]) -> BatchOut:
        docs = await self.products.get_many(list(dict.fromkeys(ids)))
        return BatchOut(items=[card(d) for d in docs])

    async def suggest(self, q: str) -> Suggestions:
        docs, _ = await self.products.search(search_filter(q=q, anchored=True), "best_selling", 0, 5)
        needle = q.casefold()
        cats = [c for c in await self._categories() if c["label"].casefold().startswith(needle)][:3]
        return Suggestions(
            products=[card(d) for d in docs],
            categories=[CategoryRef(category=c["category"], label=c["label"]) for c in cats],
        )
