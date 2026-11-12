"""SQL fixo da vitrine de produtos e do backoffice (DuckDB). Sem LLM e sem escrita.

Tudo aqui são constantes do código: nenhuma entrada do usuário vira texto de SQL. Valores
variáveis (busca, categoria, página...) entram como placeholders `?` em `Query.params`, e a
ordenação só aceita nomes de uma allowlist (`PUBLIC_SORTS`, `ADMIN_SORTS`). Nada é criado no
snapshot (sem tabela ou view): os CTEs abaixo são recalculados a cada consulta.

Modelo de dados (`item_facts`): uma linha por item vendido, com
  - pedidos cancelados/indisponíveis EXCLUÍDOS;
  - categoria = nome em português (`sem_categoria` se o produto não tem); `category_en` = tradução
    ou, sem tradução, o próprio nome em português;
  - nota do cliente: o Olist avalia o PEDIDO, não o produto. A nota média é calculada por pedido
    (AVG(review_score) agrupado por order_id) ANTES de juntar com os itens, para um pedido com
    vários itens ou várias avaliações não multiplicar linhas. A nota de um produto é a média dos
    pedidos que o contêm, contando cada pedido uma vez (`rn_*` = 1 marca a primeira linha do
    pedido dentro do produto, da categoria ou do pedido inteiro);
  - `is_bad` = nota do pedido <= 2; `is_late` = entregue depois da data estimada. Ambos ficam NULL
    (fora das médias) sem avaliação ou sem entrega, ou seja, atraso é medido só entre entregues.
"""

from typing import Any, NamedTuple

from app.schemas.product import AdminSort, PublicSort, SortOrder

MAX_RELATED = 6
MAX_TOP_SELLERS = 5
OVERVIEW_TOP_N = 10
NO_CATEGORY = "sem_categoria"


class Query(NamedTuple):
    sql: str
    params: list[Any]


PUBLIC_SORTS: dict[PublicSort, str] = {
    "units": "units_sold DESC",
    "rating": "avg_rating DESC NULLS LAST",
    "price_asc": "avg_price ASC",
    "price_desc": "avg_price DESC",
}

ADMIN_SORTS: dict[AdminSort, str] = {
    "units": "units_sold",
    "revenue": "revenue",
    "rating": "avg_rating",
    "price": "avg_price",
    "bad_review_pct": "bad_review_pct",
    "late_pct": "late_pct",
}

SORT_DIRECTIONS: dict[SortOrder, str] = {"asc": "ASC", "desc": "DESC"}

_ITEM_FACTS = f"""
review_by_order AS (
    SELECT order_id, AVG(review_score) AS order_rating
    FROM order_reviews
    WHERE review_score IS NOT NULL
    GROUP BY order_id
),
base_items AS (
    SELECT
        oi.order_id,
        oi.order_item_id,
        oi.product_id,
        oi.seller_id,
        oi.price,
        oi.freight_value,
        strftime(o.order_purchase_timestamp, '%Y-%m') AS month,
        rbo.order_rating,
        o.order_delivered_customer_date > o.order_estimated_delivery_date AS is_late,
        COALESCE(NULLIF(TRIM(p.product_category_name), ''), '{NO_CATEGORY}') AS category,
        COALESCE(
            t.product_category_name_english, NULLIF(TRIM(p.product_category_name), ''), '{NO_CATEGORY}'
        ) AS category_en,
        p.product_photos_qty AS photos_qty,
        p.product_weight_g AS weight_g,
        p.product_length_cm AS length_cm,
        p.product_height_cm AS height_cm,
        p.product_width_cm AS width_cm,
        p.product_name_length AS name_length,
        p.product_description_length AS description_length
    FROM order_items oi
    JOIN orders o
        ON o.order_id = oi.order_id AND COALESCE(o.order_status, '') NOT IN ('canceled', 'unavailable')
    JOIN products p ON p.product_id = oi.product_id
    LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
    LEFT JOIN review_by_order rbo ON rbo.order_id = oi.order_id
),
item_facts AS (
    SELECT
        *,
        order_rating <= 2 AS is_bad,
        ROW_NUMBER() OVER (PARTITION BY product_id, order_id ORDER BY order_item_id) AS rn_product,
        ROW_NUMBER() OVER (PARTITION BY category, order_id ORDER BY product_id, order_item_id) AS rn_category,
        ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY product_id, order_item_id) AS rn_order
    FROM base_items
)"""

_PRODUCT_STATS = """
product_stats AS (
    SELECT
        product_id, category, category_en, photos_qty,
        weight_g, length_cm, height_cm, width_cm, name_length, description_length,
        COUNT(*) AS units_sold,
        COUNT(DISTINCT order_id) AS orders,
        SUM(price) AS revenue,
        AVG(price) AS avg_price,
        AVG(freight_value) AS freight_avg,
        COUNT(DISTINCT seller_id) AS sellers,
        AVG(order_rating) FILTER (WHERE rn_product = 1) AS avg_rating,
        COUNT(order_rating) FILTER (WHERE rn_product = 1) AS review_count,
        100.0 * AVG(CAST(is_bad AS DOUBLE)) FILTER (WHERE rn_product = 1) AS bad_review_pct,
        100.0 * AVG(CAST(is_late AS DOUBLE)) FILTER (WHERE rn_product = 1) AS late_pct
    FROM item_facts
    GROUP BY ALL
),
ranked_products AS (
    SELECT *, RANK() OVER (ORDER BY revenue DESC) AS revenue_rank FROM product_stats
)"""

_CATEGORY_STATS = """
category_stats AS (
    SELECT
        category, category_en,
        COUNT(DISTINCT product_id) AS products,
        COUNT(*) AS units_sold,
        SUM(price) AS revenue,
        AVG(price) AS avg_price,
        AVG(order_rating) FILTER (WHERE rn_category = 1) AS avg_rating,
        100.0 * AVG(CAST(is_bad AS DOUBLE)) FILTER (WHERE rn_category = 1) AS bad_review_pct,
        100.0 * AVG(CAST(is_late AS DOUBLE)) FILTER (WHERE rn_category = 1) AS late_pct
    FROM item_facts
    GROUP BY category, category_en
),
ranked_categories AS (
    SELECT *, RANK() OVER (ORDER BY revenue DESC) AS revenue_rank FROM category_stats
)"""

_PRODUCT_SUMMARY_COLUMNS = (
    "product_id, category, category_en, avg_price, avg_rating, review_count, units_sold, photos_qty"
)
_ADMIN_ROW_COLUMNS = (
    f"{_PRODUCT_SUMMARY_COLUMNS}, revenue, freight_avg, bad_review_pct, late_pct, sellers, revenue_rank"
)
_DIMENSION_COLUMNS = "weight_g, length_cm, height_cm, width_cm, name_length, description_length"
_ADMIN_CATEGORY_COLUMNS = (
    "category, category_en, products, units_sold, revenue, avg_price, avg_rating, "
    "bad_review_pct, late_pct, revenue_rank"
)


def _with(*ctes: str) -> str:
    return "WITH " + ",".join([_ITEM_FACTS, *ctes])


def like_escape(text: str) -> str:
    """Neutraliza os curingas do LIKE: a busca do usuário é texto literal, não padrão."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _filters(q: str | None, category: str | None, min_rating: float | None) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if q and q.strip():
        escaped = like_escape(q.strip())
        # product_id por prefixo; categoria (pt ou en) por trecho.
        clauses.append(
            "(product_id ILIKE ? ESCAPE '\\' OR category ILIKE ? ESCAPE '\\' OR category_en ILIKE ? ESCAPE '\\')"
        )
        params += [f"{escaped}%", f"%{escaped}%", f"%{escaped}%"]
    if category:
        clauses.append("(category = ? OR category_en = ?)")
        params += [category, category]
    if min_rating:
        clauses.append("avg_rating >= ?")
        params.append(min_rating)
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


def _page(sql_select: str, where: str, order_by: str, page: int, page_size: int, params: list[Any]) -> Query:
    sql = f"{sql_select} {where} ORDER BY {order_by}, product_id LIMIT ? OFFSET ?"
    return Query(sql, [*params, page_size, (page - 1) * page_size])


# --- Vitrine pública -----------------------------------------------------------------------


def public_products_page(q: str | None, category: str | None, sort: PublicSort, page: int, page_size: int) -> Query:
    where, params = _filters(q, category, None)
    select = (
        f"{_with(_PRODUCT_STATS)} SELECT {_PRODUCT_SUMMARY_COLUMNS}, COUNT(*) OVER () AS total_rows FROM product_stats"
    )
    return _page(select, where, PUBLIC_SORTS[sort], page, page_size, params)


def public_products_count(q: str | None, category: str | None) -> Query:
    where, params = _filters(q, category, None)
    return Query(f"{_with(_PRODUCT_STATS)} SELECT COUNT(*) AS total_rows FROM product_stats {where}", params)


def product_summary(product_id: str) -> Query:
    sql = (
        f"{_with(_PRODUCT_STATS)} SELECT {_PRODUCT_SUMMARY_COLUMNS}, {_DIMENSION_COLUMNS} "
        "FROM product_stats WHERE product_id = ?"
    )
    return Query(sql, [product_id])


def related_products(product_id: str, category: str) -> Query:
    sql = (
        f"{_with(_PRODUCT_STATS)} SELECT {_PRODUCT_SUMMARY_COLUMNS} FROM product_stats "
        "WHERE category = ? AND product_id <> ? ORDER BY units_sold DESC, product_id LIMIT ?"
    )
    return Query(sql, [category, product_id, MAX_RELATED])


def public_categories() -> Query:
    sql = (
        f"{_with(_CATEGORY_STATS)} SELECT category, category_en, products, units_sold FROM category_stats "
        "ORDER BY units_sold DESC, category"
    )
    return Query(sql, [])


# --- Backoffice ----------------------------------------------------------------------------


def admin_products_page(
    q: str | None,
    category: str | None,
    min_rating: float | None,
    sort: AdminSort,
    order: SortOrder,
    page: int,
    page_size: int,
) -> Query:
    where, params = _filters(q, category, min_rating)
    select = f"{_with(_PRODUCT_STATS)} SELECT {_ADMIN_ROW_COLUMNS}, COUNT(*) OVER () AS total_rows FROM ranked_products"
    order_by = f"{ADMIN_SORTS[sort]} {SORT_DIRECTIONS[order]} NULLS LAST"
    return _page(select, where, order_by, page, page_size, params)


def admin_products_count(q: str | None, category: str | None, min_rating: float | None) -> Query:
    where, params = _filters(q, category, min_rating)
    return Query(f"{_with(_PRODUCT_STATS)} SELECT COUNT(*) AS total_rows FROM ranked_products {where}", params)


def admin_product(product_id: str) -> Query:
    sql = (
        f"{_with(_PRODUCT_STATS)} SELECT {_ADMIN_ROW_COLUMNS}, {_DIMENSION_COLUMNS} "
        "FROM ranked_products WHERE product_id = ?"
    )
    return Query(sql, [product_id])


def product_monthly(product_id: str) -> Query:
    sql = (
        f"{_with()} SELECT month, SUM(price) AS revenue, COUNT(*) AS units, COUNT(DISTINCT order_id) AS orders "
        "FROM item_facts WHERE product_id = ? AND month IS NOT NULL GROUP BY month ORDER BY month"
    )
    return Query(sql, [product_id])


def product_rating_distribution(product_id: str) -> Query:
    sql = (
        f"{_with()} SELECT CAST(ROUND(order_rating) AS INTEGER) AS score, COUNT(*) AS total FROM item_facts "
        "WHERE product_id = ? AND rn_product = 1 AND order_rating IS NOT NULL GROUP BY score ORDER BY score"
    )
    return Query(sql, [product_id])


def product_top_sellers(product_id: str) -> Query:
    sql = (
        f"{_with()} SELECT f.seller_id, s.seller_state, COUNT(*) AS units, SUM(f.price) AS revenue "
        "FROM item_facts f LEFT JOIN sellers s ON s.seller_id = f.seller_id WHERE f.product_id = ? "
        "GROUP BY f.seller_id, s.seller_state ORDER BY revenue DESC, f.seller_id LIMIT ?"
    )
    return Query(sql, [product_id, MAX_TOP_SELLERS])


def admin_categories(limit: int | None = None) -> Query:
    sql = (
        f"{_with(_CATEGORY_STATS)} SELECT {_ADMIN_CATEGORY_COLUMNS} "
        "FROM ranked_categories ORDER BY revenue DESC, category"
    )
    if limit is None:
        return Query(sql, [])
    return Query(f"{sql} LIMIT ?", [limit])


def top_products(limit: int) -> Query:
    sql = (
        f"{_with(_PRODUCT_STATS)} SELECT {_ADMIN_ROW_COLUMNS} FROM ranked_products "
        "ORDER BY revenue DESC, product_id LIMIT ?"
    )
    return Query(sql, [limit])


def overview_kpis() -> Query:
    sql = f"""{_with()}
SELECT
    COALESCE(SUM(price), 0) AS revenue,
    COUNT(*) AS units,
    COUNT(DISTINCT order_id) AS orders,
    SUM(price) / NULLIF(COUNT(DISTINCT order_id), 0) AS avg_ticket,
    AVG(order_rating) FILTER (WHERE rn_order = 1) AS avg_rating,
    100.0 * AVG(CAST(is_late AS DOUBLE)) FILTER (WHERE rn_order = 1) AS late_pct,
    COUNT(DISTINCT product_id) AS products,
    COUNT(DISTINCT seller_id) AS sellers,
    COUNT(DISTINCT category) AS categories
FROM item_facts"""
    return Query(sql, [])


def overview_monthly() -> Query:
    sql = (
        f"{_with()} SELECT month, SUM(price) AS revenue, COUNT(*) AS units, COUNT(DISTINCT order_id) AS orders "
        "FROM item_facts WHERE month IS NOT NULL GROUP BY month ORDER BY month"
    )
    return Query(sql, [])
