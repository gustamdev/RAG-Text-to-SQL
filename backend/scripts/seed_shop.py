"""Monta `shop_products` a partir das coleções Olist já carregadas (products, order_items, order_reviews).

Uso (a partir de backend/): uv run python scripts/seed_shop.py

Idempotente: upsert por product_id. Reexecutar atualiza o catálogo (preço, notas, medidas), mas NUNCA
mexe em `stock` nem em `created_at` de produto que já existe (só `$setOnInsert`), para não zerar vendas.
Preço = mediana de order_items.price em centavos. Nota = média das avaliações dos pedidos que contêm o
produto (o Olist avalia o pedido, não o produto). Título derivado só da categoria + 4 chars do id:
nenhum texto livre de cliente entra no catálogo. Produto sem preço ou sem venda não entra.
"""

import logging
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pymongo import MongoClient  # noqa: E402

from app.config import settings  # noqa: E402

logger = logging.getLogger("seed_shop")
NO_CATEGORY = "sem_categoria"


def _num(value):
    return None if value is None or value != value else float(value)  # NaN vira None


def _label(category: str) -> str:
    return category.replace("_", " ").capitalize()


def build_docs(db) -> list[dict]:
    """Documentos de catálogo (sem `stock`/`created_at`, que são só de inserção)."""
    prices: dict[str, list[float]] = defaultdict(list)
    orders_of: dict[str, set[str]] = defaultdict(set)
    for it in db["order_items"].find({}, {"_id": 0, "order_id": 1, "product_id": 1, "price": 1}):
        price = _num(it.get("price"))
        if price is None or price <= 0:
            continue
        prices[it["product_id"]].append(price)
        orders_of[it["product_id"]].add(it["order_id"])

    scores: dict[str, list[int]] = defaultdict(list)
    for r in db["order_reviews"].find({}, {"_id": 0, "order_id": 1, "review_score": 1}):
        if r.get("review_score") in (1, 2, 3, 4, 5):
            scores[r["order_id"]].append(int(r["review_score"]))

    docs = []
    for p in db["products"].find({}, {"_id": 0}):
        pid = p["product_id"]
        if pid not in prices:
            continue
        category = p.get("product_category_name") or NO_CATEGORY
        label = _label(category)
        marks = [s for oid in orders_of[pid] for s in scores.get(oid, [])]
        photos = p.get("product_photos_qty")
        docs.append(
            {
                "product_id": pid,
                "category": category,
                "category_label": label,
                "title": f"{label} · Modelo {pid[:4].upper()}",
                "price_cents": round(statistics.median(prices[pid]) * 100),
                "weight_g": _num(p.get("product_weight_g")),
                "length_cm": _num(p.get("product_length_cm")),
                "height_cm": _num(p.get("product_height_cm")),
                "width_cm": _num(p.get("product_width_cm")),
                "photos_qty": min(max(int(photos), 1), 5) if photos is not None and photos == photos else 1,
                "units_sold": len(prices[pid]),
                "review_count": len(marks),
                "avg_rating": round(sum(marks) / len(marks), 2) if marks else None,
                "rating_distribution": {str(n): marks.count(n) for n in (5, 4, 3, 2, 1)},
            }
        )
    return docs


def seed(db, stock: int | None = None) -> int:
    stock = settings.SHOP_FREE_STOCK_DEFAULT if stock is None else stock
    now = datetime.now(UTC)
    docs = build_docs(db)
    for d in docs:  # um upsert por produto: simples e idempotente (script manual, ~30 mil produtos)
        db["shop_products"].update_one(
            {"product_id": d["product_id"]},
            {"$set": {**d, "updated_at": now}, "$setOnInsert": {"stock": stock, "created_at": now}},
            upsert=True,
        )
    return len(docs)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    try:
        logger.info("shop_products: %d produtos semeados.", seed(client[settings.MONGO_DB_NAME]))
    finally:
        client.close()
