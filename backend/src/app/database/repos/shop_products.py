import inspect
import re

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

NO_ID = {"_id": 0}
SORTS = {
    "best_selling": [("units_sold", DESCENDING)],
    "price_asc": [("price_cents", ASCENDING)],
    "price_desc": [("price_cents", DESCENDING)],
    "rating": [("avg_rating", DESCENDING), ("review_count", DESCENDING)],
    "newest": [("created_at", DESCENDING)],
}


def search_filter(
    q: str | None = None,
    category: str | None = None,
    min_price_cents: int | None = None,
    max_price_cents: int | None = None,
    min_rating: float | None = None,
    min_reviews: int | None = None,
    in_stock: bool | None = None,
) -> dict:
    """Filtro Mongo a partir de valores já validados; `q` entra escapado (sem regex do cliente)."""
    f: dict = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        f["$or"] = [{"title": rx}, {"category_label": rx}]
    if category:
        f["category"] = category
    price = {k: v for k, v in (("$gte", min_price_cents), ("$lte", max_price_cents)) if v is not None}
    if price:
        f["price_cents"] = price
    if min_rating is not None:
        f["avg_rating"] = {"$gte": min_rating}
    if min_reviews is not None:
        f["review_count"] = {"$gte": min_reviews}
    if in_stock:
        f["stock"] = {"$gt": 0}
    return f


class ShopProductRepo:
    def __init__(self, db: AsyncDatabase):
        self.col = db["shop_products"]

    async def search(self, flt: dict, sort: str, skip: int, limit: int) -> tuple[list[dict], int]:
        order = SORTS[sort] + [("product_id", ASCENDING)]  # desempate: paginação estável
        cursor = self.col.find(flt, NO_ID).sort(order).skip(skip).limit(limit)
        return await cursor.to_list(limit), await self.col.count_documents(flt)

    async def get(self, product_id: str) -> dict | None:
        return await self.col.find_one({"product_id": product_id}, NO_ID)

    async def get_many(self, ids: list[str]) -> list[dict]:
        return await self.col.find({"product_id": {"$in": ids}}, NO_ID).to_list(len(ids))

    async def categories(self) -> list[dict]:
        cursor = self.col.aggregate(
            [
                {"$group": {"_id": "$category", "label": {"$first": "$category_label"}, "n": {"$sum": 1}}},
                {"$sort": {"n": -1, "_id": 1}},
            ]
        )
        if inspect.isawaitable(cursor):  # pymongo async: coroutine; mongomock-motor (testes): cursor direto
            cursor = await cursor
        return [{"category": d["_id"], "label": d["label"], "product_count": d["n"]} async for d in cursor]
