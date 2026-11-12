"""Backoffice /admin: só administradores. Os números abaixo foram conferidos à mão no dataset de conftest.py."""

import pytest

from tests.conftest import PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_CANCELED, PRODUCT_D, PRODUCT_UNSOLD

ADMIN = "/api/v1/admin"
ENDPOINTS = [
    f"{ADMIN}/overview",
    f"{ADMIN}/products",
    f"{ADMIN}/products/{PRODUCT_A}",
    f"{ADMIN}/categories",
]


@pytest.fixture
def admin(auth_db, analytics_engine):
    headers, _ = auth_db.create_admin()
    return headers


def _ids(body: dict) -> list[str]:
    return [item["product_id"] for item in body["items"]]


# --- Acesso --------------------------------------------------------------------------------


@pytest.mark.parametrize("url", ENDPOINTS)
def test_requires_token(client, auth_db, analytics_engine, url):
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer lixo"}).status_code == 401


@pytest.mark.parametrize("url", ENDPOINTS)
def test_non_admin_is_403(client, auth_db, analytics_engine, url):
    headers, _ = auth_db.create_non_admin()

    assert client.get(url, headers=headers).status_code == 403


@pytest.mark.parametrize("url", ENDPOINTS)
def test_admin_is_200(client, admin, url):
    assert client.get(url, headers=admin).status_code == 200


def test_auth_is_checked_before_engine_availability(client, auth_db):
    # Sem motor SQL (nenhum override): quem não é admin continua vendo 401/403, nunca 503.
    headers, _ = auth_db.create_non_admin()

    assert client.get(f"{ADMIN}/overview").status_code == 401
    assert client.get(f"{ADMIN}/overview", headers=headers).status_code == 403


def test_admin_gets_503_without_sql_engine(client, auth_db):
    headers, _ = auth_db.create_admin()

    assert client.get(f"{ADMIN}/overview", headers=headers).status_code == 503


# --- Visão geral ---------------------------------------------------------------------------


def test_overview_kpis(client, admin):
    kpis = client.get(f"{ADMIN}/overview", headers=admin).json()["kpis"]

    assert kpis == {
        "revenue": 580.0,  # 480 (A) + 50 (B) + 30 (C) + 20 (D); cancelado fora
        "units": 8,
        "orders": 5,  # o1, o2, o4, o5, o6
        "avg_ticket": 116.0,  # 580 / 5 pedidos
        "avg_rating": 3.0,  # o1=5, o2=1, o5=3, o6=3; o4 sem review
        "late_pct": 50.0,  # entregues: o1 ok, o2 atrasado, o4 ok, o6 atrasado; o5 ainda não entregue
        "products": 4,
        "sellers": 2,
        "categories": 3,
    }


def test_overview_monthly_excludes_canceled_orders(client, admin):
    monthly = client.get(f"{ADMIN}/overview", headers=admin).json()["monthly"]

    assert monthly == [
        {"month": "2018-01", "revenue": 150.0, "units": 2, "orders": 1},
        {"month": "2018-02", "revenue": 120.0, "units": 1, "orders": 1},  # o3 cancelado não conta
        {"month": "2018-03", "revenue": 310.0, "units": 5, "orders": 3},
    ]


def test_overview_tops(client, admin):
    body = client.get(f"{ADMIN}/overview", headers=admin).json()

    assert [p["product_id"] for p in body["top_products"]] == [PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_D]
    assert [c["category"] for c in body["top_categories"]] == [
        "beleza_saude",
        "categoria_sem_traducao",
        "sem_categoria",
    ]


# --- Produtos ------------------------------------------------------------------------------


def test_product_rows_metrics(client, admin):
    rows = {i["product_id"]: i for i in client.get(f"{ADMIN}/products", headers=admin).json()["items"]}

    assert set(rows) == {PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_D}  # sem cancelado e sem nunca vendido
    assert rows[PRODUCT_A] == {
        "product_id": PRODUCT_A,
        "label": "health_beauty · #a1b2c3d4",
        "category": "beleza_saude",
        "category_en": "health_beauty",
        "avg_price": 96.0,
        "avg_rating": 3.0,
        "review_count": 4,
        "units_sold": 5,
        "photos_qty": 3,
        "revenue": 480.0,
        "freight_avg": 11.2,  # (10 + 20 + 8 + 9 + 9) / 5
        "bad_review_pct": 25.0,  # só o2 (nota 1) em 4 pedidos avaliados
        "late_pct": 66.67,  # o2 e o6 atrasados; o5 não entregue fica fora: 2 de 3
        "sellers": 2,
        "rank": 1,
    }
    assert (rows[PRODUCT_B]["revenue"], rows[PRODUCT_B]["rank"], rows[PRODUCT_B]["bad_review_pct"]) == (50.0, 2, 0.0)
    assert (rows[PRODUCT_B]["late_pct"], rows[PRODUCT_B]["freight_avg"]) == (0.0, 5.0)


def test_null_metrics_when_no_review_or_no_delivery(client, admin):
    rows = {i["product_id"]: i for i in client.get(f"{ADMIN}/products", headers=admin).json()["items"]}

    without_review = rows[PRODUCT_C]
    assert without_review["avg_rating"] is None and without_review["bad_review_pct"] is None
    assert without_review["late_pct"] == 0.0 and without_review["review_count"] == 0
    assert without_review["rank"] == 3

    not_delivered = rows[PRODUCT_D]
    assert not_delivered["late_pct"] is None  # atraso só entre pedidos entregues
    assert not_delivered["bad_review_pct"] == 0.0 and not_delivered["avg_rating"] == 3.0
    assert not_delivered["category_en"] == "sem_categoria"
    assert not_delivered["rank"] == 4


def test_default_sort_is_revenue_desc_with_paging_fields(client, admin):
    body = client.get(f"{ADMIN}/products", headers=admin).json()

    assert _ids(body) == [PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_D]
    assert (body["total"], body["page"], body["page_size"]) == (4, 1, 24)


@pytest.mark.parametrize(
    ("sort", "order", "expected"),
    [
        ("revenue", "asc", [PRODUCT_D, PRODUCT_C, PRODUCT_B, PRODUCT_A]),
        ("units", "desc", [PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_D]),
        ("units", "asc", [PRODUCT_B, PRODUCT_C, PRODUCT_D, PRODUCT_A]),
        ("price", "asc", [PRODUCT_D, PRODUCT_C, PRODUCT_B, PRODUCT_A]),
        ("price", "desc", [PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_D]),
        ("rating", "desc", [PRODUCT_B, PRODUCT_A, PRODUCT_D, PRODUCT_C]),
        ("rating", "asc", [PRODUCT_A, PRODUCT_D, PRODUCT_B, PRODUCT_C]),  # nulos sempre no fim
        ("bad_review_pct", "desc", [PRODUCT_A, PRODUCT_B, PRODUCT_D, PRODUCT_C]),
        ("late_pct", "desc", [PRODUCT_A, PRODUCT_B, PRODUCT_C, PRODUCT_D]),
        ("late_pct", "asc", [PRODUCT_B, PRODUCT_C, PRODUCT_A, PRODUCT_D]),
    ],
)
def test_sorting(client, admin, sort, order, expected):
    res = client.get(f"{ADMIN}/products", params={"sort": sort, "order": order}, headers=admin)

    assert _ids(res.json()) == expected


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "freight"},
        {"sort": "revenue; DROP TABLE products"},
        {"order": "sideways"},
        {"min_rating": 6},
        {"min_rating": -1},
        {"page": 0},
        {"page_size": 101},
        {"page_size": 0},
    ],
)
def test_invalid_parameters_are_422(client, admin, params):
    assert client.get(f"{ADMIN}/products", params=params, headers=admin).status_code == 422


def test_pagination_keeps_total_and_rank(client, admin):
    page_1 = client.get(f"{ADMIN}/products", params={"page_size": 3}, headers=admin).json()
    page_2 = client.get(f"{ADMIN}/products", params={"page_size": 3, "page": 2}, headers=admin).json()
    beyond = client.get(f"{ADMIN}/products", params={"page_size": 3, "page": 5}, headers=admin).json()

    assert _ids(page_1) == [PRODUCT_A, PRODUCT_B, PRODUCT_C]
    assert _ids(page_2) == [PRODUCT_D]
    assert page_2["items"][0]["rank"] == 4  # o rank é global, não da página nem do filtro
    assert page_1["total"] == page_2["total"] == beyond["total"] == 4
    assert beyond["items"] == []


def test_filters(client, admin):
    def get(**params):
        return client.get(f"{ADMIN}/products", params=params, headers=admin).json()

    assert _ids(get(category="health_beauty")) == [PRODUCT_A, PRODUCT_B]
    assert _ids(get(category="sem_categoria")) == [PRODUCT_D]
    assert _ids(get(q="a1ff")) == [PRODUCT_B]
    assert _ids(get(q="traducao")) == [PRODUCT_C]
    assert _ids(get(min_rating=4)) == [PRODUCT_B]
    assert _ids(get(min_rating=3)) == [PRODUCT_A, PRODUCT_B, PRODUCT_D]  # sem nota (C) nunca passa de um mínimo
    assert get(min_rating=0)["total"] == 4
    combined = get(category="health_beauty", min_rating=3, sort="price", order="asc")
    assert _ids(combined) == [PRODUCT_B, PRODUCT_A] and combined["total"] == 2


def test_filtered_rank_stays_global(client, admin):
    body = client.get(f"{ADMIN}/products", params={"category": "sem_categoria"}, headers=admin).json()

    assert body["items"][0]["rank"] == 4


def test_search_wildcards_are_literal(client, admin):
    for q in ("%", "a1%", "a_b2", "' OR 1=1 --"):
        assert client.get(f"{ADMIN}/products", params={"q": q}, headers=admin).json()["items"] == []


# --- Detalhe -------------------------------------------------------------------------------


def test_product_detail(client, admin):
    body = client.get(f"{ADMIN}/products/{PRODUCT_A}", headers=admin).json()

    assert body["product_id"] == PRODUCT_A and body["revenue"] == 480.0 and body["rank"] == 1
    assert (body["weight_g"], body["length_cm"], body["height_cm"], body["width_cm"]) == (500.0, 20.0, 10.0, 15.0)
    assert (body["name_length"], body["description_length"]) == (40, 300)
    assert body["rating_distribution"] == [
        {"score": 1, "count": 1},  # o2
        {"score": 2, "count": 0},
        {"score": 3, "count": 2},  # o5 (3) e o6 (média de 4 e 2)
        {"score": 4, "count": 0},
        {"score": 5, "count": 1},  # o1
    ]
    assert body["monthly"] == [
        {"month": "2018-01", "revenue": 100.0, "units": 1, "orders": 1},
        {"month": "2018-02", "revenue": 120.0, "units": 1, "orders": 1},  # o3 cancelado fora
        {"month": "2018-03", "revenue": 260.0, "units": 3, "orders": 2},  # o5 (80) + o6 (2 x 90)
    ]
    assert body["top_sellers"] == [
        {"seller_id": "s1_seller", "seller_state": "SP", "units": 4, "revenue": 360.0},
        {"seller_id": "s2_seller", "seller_state": "RJ", "units": 1, "revenue": 120.0},
    ]


def test_detail_distribution_always_has_five_buckets(client, admin):
    body = client.get(f"{ADMIN}/products/{PRODUCT_C}", headers=admin).json()

    assert body["rating_distribution"] == [{"score": s, "count": 0} for s in range(1, 6)]
    assert body["monthly"] == [{"month": "2018-03", "revenue": 30.0, "units": 1, "orders": 1}]
    assert body["weight_g"] is None and body["avg_rating"] is None


@pytest.mark.parametrize("product_id", [PRODUCT_CANCELED, PRODUCT_UNSOLD, "nao-existe", "x' OR '1'='1"])
def test_detail_404(client, admin, product_id):
    res = client.get(f"{ADMIN}/products/{product_id}", headers=admin)

    assert res.status_code == 404
    assert res.json() == {"detail": "Produto não encontrado."}


# --- Categorias ----------------------------------------------------------------------------


def test_categories_metrics(client, admin):
    rows = client.get(f"{ADMIN}/categories", headers=admin).json()

    assert rows == [
        {
            "category": "beleza_saude",
            "category_en": "health_beauty",
            "products": 2,
            "units_sold": 6,
            "revenue": 530.0,
            "avg_price": 88.33,  # 530 / 6 unidades
            "avg_rating": 3.0,  # pedidos o1 (A e B contam uma vez), o2, o5, o6
            "bad_review_pct": 25.0,
            "late_pct": 66.67,
            "rank": 1,
        },
        {
            "category": "categoria_sem_traducao",
            "category_en": "categoria_sem_traducao",
            "products": 1,
            "units_sold": 1,
            "revenue": 30.0,
            "avg_price": 30.0,
            "avg_rating": None,
            "bad_review_pct": None,
            "late_pct": 0.0,
            "rank": 2,
        },
        {
            "category": "sem_categoria",
            "category_en": "sem_categoria",
            "products": 1,
            "units_sold": 1,
            "revenue": 20.0,
            "avg_price": 20.0,
            "avg_rating": 3.0,
            "bad_review_pct": 0.0,
            "late_pct": None,
            "rank": 3,
        },
    ]
