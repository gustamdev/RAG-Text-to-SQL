"""Guarda de SQL somente leitura (app/sql_guard.py): ataques que precisam ser barrados e consultas válidas."""

import pytest

from app.sql_guard import DEFAULT_MAX_ROWS, UnsafeQueryError, ValidatedQuery, validate_read_only_sql

ALLOWED = {"orders", "customers", "products"}


def validate(sql: str, **kwargs) -> ValidatedQuery:
    kwargs.setdefault("allowed_tables", ALLOWED)
    return validate_read_only_sql(sql, "duckdb", **kwargs)


# (sql, trecho esperado na mensagem de erro)
ATTACKS = [
    # Escrita e DDL
    pytest.param("DELETE FROM orders", "DELETE", id="delete"),
    pytest.param("INSERT INTO orders VALUES (1)", "INSERT", id="insert"),
    pytest.param("UPDATE orders SET order_status = 'x'", "UPDATE", id="update"),
    pytest.param("DROP TABLE orders", "DROP", id="drop"),
    pytest.param("CREATE TABLE copia AS SELECT * FROM orders", "CREATE", id="create-table-as"),
    pytest.param("CREATE VIEW v AS SELECT * FROM orders", "CREATE", id="create-view"),
    pytest.param("ALTER TABLE orders ADD COLUMN x INT", "ALTER", id="alter"),
    pytest.param("TRUNCATE orders", "TRUNCATE", id="truncate"),
    pytest.param("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d", "DELETE", id="delete-inside-cte"),
    pytest.param(
        "SELECT * FROM (WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d) t", "", id="delete-in-subquery"
    ),
    # Várias instruções
    pytest.param("SELECT 1; DELETE FROM orders", "exatamente 1", id="semicolon-delete"),
    pytest.param("SELECT * FROM orders; SELECT * FROM customers", "exatamente 1", id="two-selects"),
    pytest.param("SELECT * FROM orders; --", "exatamente 1", id="trailing-semicolon-comment"),
    # Exportar/ler arquivos
    pytest.param("COPY orders TO '/tmp/x.csv'", "COPY", id="copy-table"),
    pytest.param("COPY (SELECT * FROM orders) TO '/tmp/x.csv'", "COPY", id="copy-query"),
    pytest.param("EXPORT DATABASE '/tmp/dump'", "", id="export-database"),
    pytest.param("SELECT * FROM read_csv('/etc/passwd')", "read_csv", id="read_csv"),
    pytest.param("SELECT * FROM read_csv_auto('/etc/passwd')", "read_csv_auto", id="read_csv_auto"),
    pytest.param("SELECT * FROM read_parquet('/data/x.parquet')", "read_parquet", id="read_parquet"),
    pytest.param("SELECT * FROM read_json('/data/x.json')", "read_json", id="read_json"),
    pytest.param("SELECT read_text('/etc/passwd')", "read_text", id="read_text-scalar"),
    pytest.param("SELECT * FROM glob('/*')", "glob", id="glob"),
    pytest.param("SELECT * FROM orders o, read_csv('/etc/passwd') r", "read_csv", id="read_csv-in-join"),
    pytest.param("SELECT * FROM \"read_csv\"('/etc/passwd')", "read_csv", id="read_csv-quoted"),
    pytest.param("SELECT * FROM parquet_scan('x')", "Funções de tabela", id="parquet_scan"),
    pytest.param("SELECT * FROM range(100000000000)", "Funções de tabela", id="range-table-function"),
    pytest.param("SELECT * FROM duckdb_tables()", "Funções de tabela", id="duckdb_tables"),
    pytest.param("SELECT * FROM '/etc/passwd'", "fora do catálogo", id="file-path-as-table"),
    # Controle do banco
    pytest.param("PRAGMA database_list", "PRAGMA", id="pragma"),
    pytest.param("ATTACH '/tmp/outro.db' AS outro", "ATTACH", id="attach"),
    pytest.param("INSTALL httpfs", "INSTALL", id="install"),
    pytest.param("LOAD httpfs", "COMMAND", id="load"),
    pytest.param("SET enable_external_access = true", "SET", id="set"),
    pytest.param("CALL pragma_version()", "COMMAND", id="call"),
    pytest.param("VACUUM", "COMMAND", id="vacuum"),
    # Escopo de tabelas
    pytest.param("SELECT * FROM secret_table", "fora do catálogo", id="table-outside-catalog"),
    pytest.param("SELECT * FROM information_schema.tables", "fora do catálogo", id="information_schema"),
    pytest.param("SELECT * FROM main.secret_table", "fora do catálogo", id="schema-qualified-outside"),
    pytest.param(
        "SELECT * FROM orders WHERE order_id IN (SELECT id FROM secret_table)", "secret_table", id="subquery-outside"
    ),
    pytest.param("SELECT order_id FROM orders UNION SELECT id FROM secret_table", "secret_table", id="union-outside"),
    pytest.param("WITH a AS (SELECT * FROM secret_table) SELECT * FROM a", "secret_table", id="cte-outside"),
    pytest.param(
        "WITH orders AS (SELECT * FROM secret_table) SELECT * FROM orders", "secret_table", id="cte-named-like-allowed"
    ),
]


@pytest.mark.parametrize(("sql", "message"), ATTACKS)
def test_attack_is_rejected(sql, message):
    with pytest.raises(UnsafeQueryError) as exc:
        validate(sql)

    assert message.lower() in str(exc.value).lower()


def test_comment_hiding_a_second_statement_is_rejected():
    with pytest.raises(UnsafeQueryError, match="exatamente 1"):
        validate("SELECT 1 /* ; */ ; DROP TABLE orders")


@pytest.mark.parametrize(
    "sql",
    [
        "/* DROP TABLE orders */ SELECT * FROM orders",
        "SELECT * FROM orders -- ; DROP TABLE orders",
    ],
)
def test_command_inside_comment_is_just_a_comment(sql):
    validated = validate(sql)

    # O comentário continua sendo comentário: só `orders` é lida e nenhuma instrução extra surge.
    assert validated.tables == ["orders"]
    assert validated.row_limit == DEFAULT_MAX_ROWS


def test_unknown_dialect_is_a_value_error_not_a_pass():
    with pytest.raises(ValueError, match="Dialeto"):
        validate_read_only_sql("SELECT 1", "klingon")


def test_unparseable_sql_is_rejected():
    with pytest.raises(UnsafeQueryError, match="inválido"):
        validate("SELEC FROM WHERE ((")


def test_without_allowed_tables_any_table_name_is_accepted():
    assert validate("SELECT * FROM qualquer_coisa", allowed_tables=None).tables == ["qualquer_coisa"]


@pytest.mark.parametrize(
    ("sql", "tables"),
    [
        pytest.param("SELECT * FROM orders", ["orders"], id="simple"),
        pytest.param("FROM orders", ["orders"], id="duckdb-from-first"),
        pytest.param("SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY 2 DESC", ["orders"], id="aggregate"),
        pytest.param(
            "WITH recent AS (SELECT * FROM orders WHERE order_status = 'delivered') SELECT * FROM recent",
            ["orders"],
            id="with",
        ),
        pytest.param(
            "SELECT o.order_id, c.customer_id FROM orders o JOIN customers c ON c.customer_id = o.customer_id",
            ["customers", "orders"],
            id="join",
        ),
        pytest.param("SELECT * FROM (SELECT * FROM orders) t", ["orders"], id="subquery"),
        pytest.param(
            "SELECT * FROM orders WHERE customer_id IN (SELECT customer_id FROM customers)",
            ["customers", "orders"],
            id="subquery-in-where",
        ),
        pytest.param(
            "SELECT order_id FROM orders UNION ALL SELECT customer_id FROM customers",
            ["customers", "orders"],
            id="union",
        ),
        pytest.param("SELECT 1", [], id="no-table"),
    ],
)
def test_valid_query_is_accepted_with_limit_guaranteed(sql, tables):
    validated = validate(sql)

    assert validated.tables == tables
    assert validated.dialect == "duckdb"
    assert validated.row_limit == DEFAULT_MAX_ROWS
    assert f"LIMIT {DEFAULT_MAX_ROWS}" in validated.sql


def test_enormous_limit_is_reduced():
    validated = validate("SELECT * FROM orders LIMIT 99999999999", max_rows=100)

    assert validated.row_limit == 100
    assert validated.sql.endswith("LIMIT 100")
    assert "99999999999" not in validated.sql


def test_limit_inside_the_cap_is_kept():
    validated = validate("SELECT * FROM orders LIMIT 10")

    assert validated.row_limit == 10
    assert validated.sql.endswith("LIMIT 10")


def test_missing_limit_is_added_to_the_whole_union():
    validated = validate("SELECT order_id FROM orders UNION SELECT customer_id FROM customers", max_rows=50)

    assert validated.sql.endswith("LIMIT 50")
    assert validated.row_limit == 50


def test_validated_sql_is_normalized_for_the_dialect():
    assert validate("select * from orders", max_rows=5).sql == "SELECT * FROM orders LIMIT 5"


# Regressão: CTE com o mesmo nome de uma tabela real não pode esconder a tabela da allowlist.
@pytest.mark.parametrize(
    "sql",
    [
        "WITH tables AS (SELECT * FROM information_schema.tables) SELECT * FROM tables",
        "WITH secret_table AS (SELECT * FROM secret_table) SELECT * FROM secret_table",
    ],
)
def test_cte_shadowing_does_not_bypass_table_allowlist(sql):
    with pytest.raises(UnsafeQueryError):
        validate(sql)


@pytest.mark.parametrize(
    "sql",
    [
        # CTE declarada DEPOIS da referência não esconde a tabela real.
        "WITH x AS (SELECT * FROM pg_tables), pg_tables AS (SELECT 1) SELECT * FROM x",
        # CTE homônima dentro de uma subconsulta não vale para a consulta de fora.
        "SELECT * FROM secret, (WITH secret AS (SELECT 1) SELECT * FROM secret) x",
        # Tabela de outro schema/catálogo.
        "SELECT * FROM other.main.orders",
        "SELECT * FROM system.main.orders",
        "SELECT * FROM information_schema.tables",
        "SELECT getenv('OPENAI_API_KEY')",
        "SELECT current_database()",
    ],
)
def test_scope_and_qualifier_bypasses_are_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        validate(sql)


def test_recursive_cte_may_reference_itself():
    sql = "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM t WHERE n < 5) SELECT * FROM t"
    assert validate(sql).tables == []


def test_later_cte_may_reference_an_earlier_one():
    validated = validate("WITH a AS (SELECT order_id FROM orders), b AS (SELECT * FROM a) SELECT * FROM b")
    assert validated.tables == ["orders"]


def test_main_qualified_table_is_accepted():
    assert validate("SELECT * FROM main.orders").tables == ["orders"]


def test_current_setting_is_forbidden():
    with pytest.raises(UnsafeQueryError):
        validate("SELECT current_setting('home_directory')")


@pytest.mark.parametrize(
    "sql",
    ["SELECT * FROM orders, customers, products", "SELECT * FROM orders CROSS JOIN customers CROSS JOIN products"],
)
def test_cartesian_product_blocked(sql):
    with pytest.raises(UnsafeQueryError, match="produto cartesiano"):
        validate(sql)


def test_joins_with_condition_pass():
    validate("SELECT * FROM orders o JOIN customers c ON o.id = c.id JOIN products p USING (id)")
    validate("SELECT * FROM orders, customers WHERE orders.id = customers.id")
