"""Monta `shop_products` a partir das coleções Olist já carregadas (products, order_items, order_reviews).

Uso (a partir de backend/): uv run python scripts/seed_shop.py [--restock]

Idempotente: upsert por product_id. Reexecutar atualiza o catálogo (preço, notas, medidas), mas NUNCA
mexe em `stock` de produto que já existe (só `$setOnInsert`), para não zerar vendas;
`--restock` reaplica a regra de estoque (initial_stock) a TODOS os produtos, sobrescrevendo o estoque atual.
`created_at` é estável:
1ª data de venda (min de order_items.shipping_limit_date) ou data fixa; reexecutar não muda a ordem "newest".
Preço = mediana de order_items.price em centavos. Nota = média das avaliações dos pedidos que contêm o
produto (o Olist avalia o pedido, não o produto). Título derivado só da categoria + 4 chars do id:
nenhum texto livre de cliente entra no catálogo. Produto sem preço ou sem venda não entra.
"""

import hashlib
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
FALLBACK_CREATED = datetime(2017, 1, 1, tzinfo=UTC)


def _num(value):
    return None if value is None or value != value else float(value)  # NaN vira None


def _text(value) -> str | None:
    return value.strip() or None if isinstance(value, str) else None  # coluna ausente/NaN vira None


def _label(category: str) -> str:
    return category.replace("_", " ").capitalize()


def _when(value) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def build_docs(db) -> list[dict]:
    """Documentos de catálogo (sem `stock`, que é só de inserção)."""
    prices: dict[str, list[float]] = defaultdict(list)
    orders_of: dict[str, set[str]] = defaultdict(set)
    first_sale: dict[str, datetime] = {}
    items = db["order_items"].find({}, {"_id": 0, "order_id": 1, "product_id": 1, "price": 1, "shipping_limit_date": 1})
    for it in items:
        price = _num(it.get("price"))
        if price is None or price <= 0:
            continue
        prices[it["product_id"]].append(price)
        orders_of[it["product_id"]].add(it["order_id"])
        when = _when(it.get("shipping_limit_date"))
        if when and (it["product_id"] not in first_sale or when < first_sale[it["product_id"]]):
            first_sale[it["product_id"]] = when

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
        name = _text(p.get("product_name"))
        extra = {
            k: v
            for k, v in (
                ("brand", _text(p.get("product_brand"))),
                ("description", _text(p.get("product_description"))),
                ("image_key", _text(p.get("image_key"))),
            )
            if v
        }
        docs.append(
            {
                "product_id": pid,
                "category": category,
                "category_label": label,
                "created_at": first_sale.get(pid, FALLBACK_CREATED),
                "title": name or f"{label} · Modelo {pid[:4].upper()}",
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
                **extra,
            }
        )
    return docs


def initial_stock(product_id: str, units_sold: int) -> int:
    """Estoque determinístico (hash do id + popularidade): ~2% zerados, ~10% baixos (1-5), o resto 15-150,
    com mais unidades para quem vende mais."""
    h = int(hashlib.sha256(product_id.encode()).hexdigest()[:8], 16) % 1000
    if h < 20:
        return 0
    if h < 120:
        return 1 + h % 5
    return min(15 + h % 60 + 2 * min(units_sold, 40), 150)


def seed(db, stock: int | None = None, restock: bool = False) -> int:
    """`stock` fixo (testes/legado) ou, por padrão, `initial_stock` por produto. `restock` sobrescreve os existentes."""
    now = datetime.now(UTC)
    docs = build_docs(db)
    for d in docs:  # um upsert por produto: simples e idempotente (script manual, ~30 mil produtos)
        value = initial_stock(d["product_id"], d["units_sold"]) if stock is None else stock
        update = {"$set": {**d, "updated_at": now}}
        update["$set" if restock else "$setOnInsert"] = (
            {**update["$set"], "stock": value} if restock else {"stock": value}
        )
        db["shop_products"].update_one({"product_id": d["product_id"]}, update, upsert=True)
    return len(docs)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    try:
        n = seed(client[settings.MONGO_DB_NAME], restock="--restock" in sys.argv[1:])
        logger.info("shop_products: %d produtos semeados.", n)
    finally:
        client.close()
