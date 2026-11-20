"""E2: catálogo público, batch e semeadura de shop_products."""

import sys
from pathlib import Path

import mongomock
import pytest
from shop_helpers import V1, shop  # noqa: F401

from app.config import settings

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed_shop  # noqa: E402

P = f"{V1}/shop/products"


@pytest.fixture
def catalog(shop):  # noqa: F811
    shop.product("aaaa0001", price_cents=5000, avg_rating=4.5, review_count=10, units_sold=100, stock=3)
    shop.product("bbbb0002", price_cents=1500, avg_rating=3.0, review_count=2, units_sold=500, stock=0)
    shop.product(
        "cccc0003", category="esporte_lazer", category_label="Esporte lazer", title="Esporte lazer · Modelo CCCC",
        price_cents=9900, avg_rating=None, review_count=0, units_sold=7, stock=9,
    )  # fmt: skip
    shop.product("dddd0004", price_cents=2500, avg_rating=4.9, review_count=40, units_sold=50, stock=1)
    return shop


def ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [i["product_id"] for i in response.json()["items"]]


def test_default_sort_is_best_selling(catalog):
    assert ids(catalog.client.get(P)) == ["bbbb0002", "aaaa0001", "dddd0004", "cccc0003"]


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("price_asc", ["bbbb0002", "dddd0004", "aaaa0001", "cccc0003"]),
        ("price_desc", ["cccc0003", "aaaa0001", "dddd0004", "bbbb0002"]),
        ("rating", ["dddd0004", "aaaa0001", "bbbb0002", "cccc0003"]),
    ],
)
def test_sorts(catalog, sort, expected):
    assert ids(catalog.client.get(P, params={"sort": sort})) == expected


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"category": "esporte_lazer"}, ["cccc0003"]),
        ({"q": "esporte"}, ["cccc0003"]),
        ({"q": "modelo aaaa"}, ["aaaa0001"]),
        ({"min_price_cents": 2000, "max_price_cents": 6000, "sort": "price_asc"}, ["dddd0004", "aaaa0001"]),
        ({"min_rating": 4, "sort": "price_asc"}, ["dddd0004", "aaaa0001"]),
        ({"min_reviews": 10, "sort": "price_asc"}, ["dddd0004", "aaaa0001"]),
        ({"in_stock": True, "sort": "price_asc"}, ["dddd0004", "aaaa0001", "cccc0003"]),
        ({"q": ".*"}, []),  # regex do cliente é escapado
    ],
)
def test_filters(catalog, params, expected):
    assert ids(catalog.client.get(P, params=params)) == expected


def test_pagination(catalog):
    first = catalog.client.get(P, params={"page_size": 3, "sort": "price_asc"}).json()
    second = catalog.client.get(P, params={"page_size": 3, "page": 2, "sort": "price_asc"}).json()
    assert (first["total"], first["page"], first["page_size"]) == (4, 1, 3)
    assert [i["product_id"] for i in first["items"]] + [i["product_id"] for i in second["items"]] == [
        "bbbb0002", "dddd0004", "aaaa0001", "cccc0003",
    ]  # fmt: skip
    assert catalog.client.get(P, params={"page": 99}).json() == {"items": [], "total": 4, "page": 99, "page_size": 24}


@pytest.mark.parametrize("params", [{"page_size": 49}, {"page_size": 0}, {"page": 0}, {"min_rating": 6}, {"sort": "x"}])
def test_invalid_query_422(catalog, params):
    assert catalog.client.get(P, params=params).status_code == 422


def test_categories_with_count(catalog):
    body = catalog.client.get(f"{P}/categories").json()
    assert body == [
        {"category": "cama_mesa_banho", "label": "Cama mesa banho", "product_count": 3},
        {"category": "esporte_lazer", "label": "Esporte lazer", "product_count": 1},
    ]


def test_detail_and_404(catalog):
    body = catalog.client.get(f"{P}/aaaa0001").json()
    assert body["price_cents"] == 5000 and body["weight_g"] == 1000.0 and "rating_distribution" in body
    r = catalog.client.get(f"{P}/nao-existe")
    assert r.status_code == 404 and r.json() == {"detail": "Produto não encontrado."}


def test_suggest(catalog):
    body = catalog.client.get(f"{P}/suggest", params={"q": "esporte"}).json()
    assert [p["product_id"] for p in body["products"]] == ["cccc0003"]
    assert body["categories"] == [{"category": "esporte_lazer", "label": "Esporte lazer"}]
    assert catalog.client.get(f"{P}/suggest", params={"q": "e"}).status_code == 422


def test_batch_current_price_and_stock_unknown_omitted(catalog):
    catalog.set_product("aaaa0001", price_cents=5100, stock=2)
    r = catalog.client.post(f"{P}/batch", json={"ids": ["aaaa0001", "aaaa0001", "zzzz", "bbbb0002"]})
    by_id = {i["product_id"]: i for i in r.json()["items"]}
    assert set(by_id) == {"aaaa0001", "bbbb0002"}
    assert (by_id["aaaa0001"]["price_cents"], by_id["aaaa0001"]["stock"]) == (5100, 2)


def test_batch_limits(catalog):
    assert catalog.client.post(f"{P}/batch", json={"ids": [f"p{i}" for i in range(50)]}).status_code == 200
    assert catalog.client.post(f"{P}/batch", json={"ids": [f"p{i}" for i in range(51)]}).status_code == 422
    assert catalog.client.post(f"{P}/batch", json={"ids": []}).status_code == 422
    assert catalog.client.post(f"{P}/batch", json={"ids": ["a"], "x": 1}).status_code == 422


def test_public_rate_limit(catalog, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT", 2)
    codes = [catalog.client.get(f"{P}/categories").status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# --- seed ---------------------------------------------------------------------------------------


def _olist():
    db = mongomock.MongoClient()["olist"]
    db["products"].insert_many(
        [
            {"product_id": "p1" + "0" * 30, "product_category_name": "cama_mesa_banho", "product_weight_g": 800.0,
             "product_length_cm": 20.0, "product_height_cm": 5.0, "product_width_cm": 10.0, "product_photos_qty": 9},
            {"product_id": "p2" + "0" * 30, "product_category_name": None, "product_weight_g": None,
             "product_length_cm": None, "product_height_cm": None, "product_width_cm": None,
             "product_photos_qty": None},
            {"product_id": "p3" + "0" * 30, "product_category_name": "nunca_vendido", "product_weight_g": 1.0,
             "product_length_cm": 1.0, "product_height_cm": 1.0, "product_width_cm": 1.0, "product_photos_qty": 1},
        ]
    )  # fmt: skip
    p1, p2 = "p1" + "0" * 30, "p2" + "0" * 30
    db["order_items"].insert_many(
        [
            {"order_id": "o1", "product_id": p1, "price": 10.0},
            {"order_id": "o2", "product_id": p1, "price": 20.0},
            {"order_id": "o3", "product_id": p1, "price": 30.5},
            {"order_id": "o3", "product_id": p2, "price": 7.99},
        ]
    )
    db["order_reviews"].insert_many(
        [
            {"order_id": "o1", "review_score": 5, "review_comment_message": "texto livre do cliente"},
            {"order_id": "o2", "review_score": 4},
            {"order_id": "o3", "review_score": 2},
        ]
    )
    return db


def test_seed_prices_positive_stock_nonneg():
    db = _olist()
    assert seed_shop.seed(db) == 2  # p3 nunca vendido fica fora
    docs = {d["product_id"][:2]: d for d in db["shop_products"].find()}
    assert docs["p1"]["price_cents"] == 2000  # mediana de 10, 20 e 30,5
    assert docs["p2"]["price_cents"] == 799
    assert all(d["price_cents"] > 0 and d["stock"] >= 0 for d in docs.values())
    assert docs["p1"]["stock"] == seed_shop.initial_stock(docs["p1"]["product_id"], 3)
    assert (docs["p1"]["review_count"], docs["p1"]["avg_rating"]) == (3, 3.67)
    assert docs["p1"]["rating_distribution"] == {"5": 1, "4": 1, "3": 0, "2": 1, "1": 0}
    assert docs["p1"]["photos_qty"] == 5 and docs["p2"]["photos_qty"] == 1
    assert docs["p2"]["category"] == "sem_categoria" and docs["p2"]["weight_g"] is None
    assert docs["p1"]["title"] == "Cama mesa banho · Modelo P100"
    assert "texto livre" not in str(docs)  # nada de texto de cliente no catálogo


def test_seed_idempotent_keeps_stock():
    db = _olist()
    seed_shop.seed(db)
    db["shop_products"].update_one({"product_id": "p1" + "0" * 30}, {"$set": {"stock": 1}})
    db["order_items"].insert_one({"order_id": "o9", "product_id": "p1" + "0" * 30, "price": 100.0})
    seed_shop.seed(db)
    assert db["shop_products"].count_documents({}) == 2
    p1 = db["shop_products"].find_one({"product_id": "p1" + "0" * 30})
    assert p1["stock"] == 1 and p1["units_sold"] == 4  # catálogo atualiza, estoque não volta ao padrão


def test_seed_enriched_columns_optional():
    db = _olist()
    p1 = "p1" + "0" * 30
    db["products"].update_one(
        {"product_id": p1},
        {"$set": {"product_name": " Toalha Azul ", "product_brand": "Acme", "image_key": f"product-images/{p1}.jpg"}},
    )
    seed_shop.seed(db)
    docs = {d["product_id"][:2]: d for d in db["shop_products"].find()}
    assert docs["p1"]["title"] == "Toalha Azul" and docs["p1"]["brand"] == "Acme"
    assert docs["p1"]["image_key"] == f"product-images/{p1}.jpg" and "description" not in docs["p1"]
    assert docs["p2"]["title"].endswith("Modelo P200") and "image_key" not in docs["p2"]
