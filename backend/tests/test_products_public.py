"""Vitrine pública (/products, /categories): sem token, sobre o dataset mínimo de conftest.py."""

from types import SimpleNamespace

import pytest

from app.api.deps import get_sql_engine
from tests.conftest import PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_CANCELED, PRODUCT_D, PRODUCT_UNSOLD

PRODUCTS = "/api/v1/products"


def _ids(body: dict) -> list[str]:
    return [item["product_id"] for item in body["items"]]


def test_list_is_public_and_sorted_by_units_by_default(client, analytics_engine):
    res = client.get(PRODUCTS)

    assert res.status_code == 200
    body = res.json()
    # A vende 5; os demais vendem 1 e desempatam por id. Cancelado e nunca vendido não aparecem.
    assert _ids(body) == [PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_D]
    assert (body["total"], body["page"], body["page_size"]) == (4, 1, 24)
    assert PRODUCT_CANCELED not in _ids(body) and PRODUCT_UNSOLD not in _ids(body)


def test_summary_contract_and_numbers(client, analytics_engine):
    item = client.get(PRODUCTS).json()["items"][0]

    assert item == {
        "product_id": PRODUCT_A,
        "label": "health_beauty · #a1b2c3d4",
        "category": "beleza_saude",
        "category_en": "health_beauty",
        "avg_price": 96.0,  # (100 + 120 + 80 + 90 + 90) / 5; o item do pedido cancelado fica de fora
        "avg_rating": 3.0,  # pedidos o1=5, o2=1, o5=3, o6=3 (média de 4 e 2), cada pedido uma vez
        "review_count": 4,
        "units_sold": 5,
        "photos_qty": 3,
    }


def test_public_payload_has_no_backoffice_fields(client, analytics_engine):
    item = client.get(PRODUCTS).json()["items"][0]

    for field in ("revenue", "freight_avg", "bad_review_pct", "late_pct", "sellers", "rank"):
        assert field not in item


def test_missing_category_and_missing_translation(client, analytics_engine):
    by_id = {i["product_id"]: i for i in client.get(PRODUCTS).json()["items"]}

    no_translation = by_id[PRODUCT_C]
    assert (no_translation["category"], no_translation["category_en"]) == ("categoria_sem_traducao",) * 2
    assert no_translation["label"] == "categoria_sem_traducao · #c3c3c3c3"
    assert no_translation["avg_rating"] is None and no_translation["review_count"] == 0
    assert no_translation["photos_qty"] is None

    no_category = by_id[PRODUCT_D]
    assert (no_category["category"], no_category["category_en"]) == ("sem_categoria",) * 2


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        ("units", [PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_D]),
        ("price_asc", [PRODUCT_D, PRODUCT_C, PRODUCT_B, PRODUCT_A]),
        ("price_desc", [PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_D]),
        ("rating", [PRODUCT_B, PRODUCT_A, PRODUCT_D, PRODUCT_C]),  # sem nota vai para o fim
    ],
)
def test_sort_options(client, analytics_engine, sort, expected):
    assert _ids(client.get(PRODUCTS, params={"sort": sort}).json()) == expected


def test_invalid_sort_is_422(client, analytics_engine):
    assert client.get(PRODUCTS, params={"sort": "price; DROP TABLE products"}).status_code == 422


def test_pagination(client, analytics_engine):
    first = client.get(PRODUCTS, params={"page_size": 3}).json()
    second = client.get(PRODUCTS, params={"page_size": 3, "page": 2}).json()
    beyond = client.get(PRODUCTS, params={"page_size": 3, "page": 9}).json()

    assert _ids(first) == [PRODUCT_A, PRODUCT_B, PRODUCT_C]
    assert _ids(second) == [PRODUCT_D]
    assert first["total"] == second["total"] == beyond["total"] == 4  # total vale mesmo além da última página
    assert beyond["items"] == []


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 101}, {"page": "x"}])
def test_invalid_pagination_is_422(client, analytics_engine, params):
    assert client.get(PRODUCTS, params=params).status_code == 422


def test_filter_by_category_in_either_language(client, analytics_engine):
    portuguese = client.get(PRODUCTS, params={"category": "beleza_saude"}).json()
    english = client.get(PRODUCTS, params={"category": "health_beauty"}).json()

    assert _ids(portuguese) == _ids(english) == [PRODUCT_A, PRODUCT_B]
    assert portuguese["total"] == 2


def test_search_by_id_prefix_and_category(client, analytics_engine):
    assert _ids(client.get(PRODUCTS, params={"q": "a1"}).json()) == [PRODUCT_A, PRODUCT_B]
    assert _ids(client.get(PRODUCTS, params={"q": "A1B2"}).json()) == [PRODUCT_A]  # sem diferenciar maiúsculas
    assert _ids(client.get(PRODUCTS, params={"q": "health"}).json()) == [PRODUCT_A, PRODUCT_B]
    assert _ids(client.get(PRODUCTS, params={"q": "traducao"}).json()) == [PRODUCT_C]
    # O prefixo vale só para o id: um trecho do meio do id não casa.
    assert client.get(PRODUCTS, params={"q": "ffee"}).json()["items"] == []


@pytest.mark.parametrize("q", ["%", "a1%", "%1b2", "a_b2", "beleza_saud_", "\\", "' OR 1=1 --"])
def test_search_treats_wildcards_and_quotes_as_literal_text(client, analytics_engine, q):
    res = client.get(PRODUCTS, params={"q": q})

    assert res.status_code == 200
    assert res.json()["items"] == []  # nenhum id/categoria contém esse texto literal


def test_blank_search_returns_everything(client, analytics_engine):
    assert client.get(PRODUCTS, params={"q": "   "}).json()["total"] == 4


def test_detail_has_dimensions_and_related(client, analytics_engine):
    res = client.get(f"{PRODUCTS}/{PRODUCT_A}")

    assert res.status_code == 200
    body = res.json()
    assert body["product_id"] == PRODUCT_A and body["units_sold"] == 5
    assert (body["weight_g"], body["length_cm"], body["height_cm"], body["width_cm"]) == (500.0, 20.0, 10.0, 15.0)
    assert (body["name_length"], body["description_length"]) == (40, 300)
    # Mesma categoria, sem o próprio produto: o produto cancelado (mesma categoria) não entra.
    assert [r["product_id"] for r in body["related"]] == [PRODUCT_B]
    assert "revenue" not in body


def test_detail_with_null_dimensions(client, analytics_engine):
    body = client.get(f"{PRODUCTS}/{PRODUCT_C}").json()

    assert body["weight_g"] is None and body["name_length"] is None
    assert body["related"] == []


@pytest.mark.parametrize("product_id", [PRODUCT_CANCELED, PRODUCT_UNSOLD, "nao-existe", "' OR 1=1 --"])
def test_detail_404_when_product_has_no_valid_sales(client, analytics_engine, product_id):
    res = client.get(f"{PRODUCTS}/{product_id}")

    assert res.status_code == 404
    assert res.json() == {"detail": "Produto não encontrado."}


def test_categories_ordered_by_units(client, analytics_engine):
    res = client.get("/api/v1/categories")

    assert res.status_code == 200
    assert res.json() == [
        {"category": "beleza_saude", "category_en": "health_beauty", "products": 2, "units_sold": 6},
        {"category": "categoria_sem_traducao", "category_en": "categoria_sem_traducao", "products": 1, "units_sold": 1},
        {"category": "sem_categoria", "category_en": "sem_categoria", "products": 1, "units_sold": 1},
    ]


def test_503_when_sql_engine_is_unavailable(client, analytics_engine):
    # Sem o override do fixture, a dependência real olha o motor guardado no estado da app (QueryRunner).
    client.app.dependency_overrides.pop(get_sql_engine)
    client.app.state.query_runner = SimpleNamespace(engine=analytics_engine)
    analytics_engine.close()

    res = client.get(PRODUCTS)

    assert res.status_code == 503
    assert res.json()["detail"]


def test_503_without_any_engine(client):
    # Sem override e sem lifespan (nenhum query_runner no estado da app): 503, não erro 500.
    assert not hasattr(client.app.state, "query_runner")

    assert client.get(PRODUCTS).status_code == 503


def test_engine_is_found_through_the_query_runner_state(client, analytics_engine):
    client.app.dependency_overrides.pop(get_sql_engine)
    client.app.state.query_runner = SimpleNamespace(engine=analytics_engine)

    assert client.get(PRODUCTS).status_code == 200


def test_public_routes_are_rate_limited_per_ip(client, analytics_engine, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT", 2)

    assert client.get(PRODUCTS).status_code == 200
    assert client.get(PRODUCTS).status_code == 200
    assert client.get(PRODUCTS).status_code == 429
