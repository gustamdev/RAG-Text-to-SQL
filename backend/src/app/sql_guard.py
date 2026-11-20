"""Guarda de SQL somente leitura: a segunda barreira, depois do prompt do agente.

`validate_read_only_sql` aceita uma única consulta SELECT/WITH, percorre a árvore inteira
(CTEs, subconsultas, UNIONs) atrás de operações e funções proibidas, confere as tabelas contra
o catálogo e garante um LIMIT. A terceira barreira é do próprio motor (`database/sql_engine.py`):
conexão somente leitura, sem acesso externo e com timeout nativo.

Este módulo não depende de prompts, agente nem banco: pode ser importado por qualquer camada.
"""

from typing import Annotated

import sqlglot
from langsmith import traceable
from pydantic import AfterValidator, BaseModel
from sqlglot import exp
from sqlglot.dialects.dialect import Dialects
from sqlglot.errors import SqlglotError

DEFAULT_MAX_ROWS = 500
MAX_ROWS_CAP = 5000
MAX_BARE_JOINS = 1  # FROM a, b, c / CROSS JOIN sem ON: produto cartesiano; 1 vírgula ainda passa (a, b WHERE ...)


# Política de tabelas da loja (E7): o agente só enxerga as views projetadas sem PII; coleções brutas
# (`shop_*`, users, golden_data) são barradas mesmo que um dia apareçam no snapshot.
SHOP_VIEW_TABLES = frozenset(
    {"shop_orders_view", "shop_order_items_view", "shop_payments_view", "shop_customers_view", "shop_products_view"}
)
FORBIDDEN_TABLES = frozenset({"users", "golden_data"})
# Cruzar a loja com estas tabelas do Olist permitiria reidentificar clientes (CEP/UF + datas).
_OLIST_REIDENTIFYING = frozenset({"customers", "geolocation"})


def is_forbidden_table(name: str) -> bool:
    lowered = name.lower()
    return lowered in FORBIDDEN_TABLES or (lowered.startswith("shop_") and lowered not in SHOP_VIEW_TABLES)


def check_dialect(value: str) -> str:
    dialect = value.strip().lower()
    supported = {d.value for d in Dialects if d.value}
    if dialect not in supported:
        raise ValueError(f"Dialeto SQL não suportado: {value!r}. Use um de: {sorted(supported)}")
    return dialect


SQLDialect = Annotated[str, AfterValidator(check_dialect)]


class UnsafeQueryError(ValueError):
    pass


class ValidatedQuery(BaseModel):
    sql: str
    dialect: str
    tables: list[str]
    row_limit: int


_FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Into,  # SELECT ... INTO cria tabela
    exp.Copy,
    exp.LoadData,
    exp.Command,  # fallback do sqlglot para instrução que ele não entende
    exp.Set,
    exp.Use,
    exp.Grant,
    exp.Revoke,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Lock,  # FOR UPDATE / FOR SHARE
    exp.Pragma,
    exp.Analyze,
    exp.Cache,
    exp.Uncache,
    exp.Refresh,
    exp.Kill,
    exp.Execute,
    exp.Declare,
    exp.Comment,
    exp.Attach,
    exp.Detach,
    exp.Install,
    exp.Export,
)

# Funções que leem arquivos, abrem conexões, alteram estado da sessão/sequência ou travam o banco.
_FORBIDDEN_FUNCTIONS = frozenset(
    {
        "pg_sleep",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "dblink",
        "dblink_exec",
        "set_config",
        "current_setting",
        "getenv",
        "current_database",
        "current_schema",
        "current_schemas",
        "current_catalog",
        "nextval",
        "setval",
        "sleep",
        "benchmark",
        "load_file",
        "get_lock",
        "release_lock",
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "read_json",
        "read_json_auto",
        "read_text",
        "read_blob",
        "read_ndjson",
        "glob",
        "openrowset",
        "opendatasource",
        "openquery",
        "xp_cmdshell",
        "sys_exec",
        "query_table",
        "sqlite_attach",
    }
)


def _function_names(node: exp.Func) -> set[str]:
    names = {node.sql_name().lower()}
    if isinstance(node, exp.Anonymous):
        names.add(node.name.lower())
    return names


def _literal_int(node: exp.Expression | None) -> int | None:
    if isinstance(node, exp.Literal) and not node.is_string:
        try:
            return int(node.this)
        except ValueError:
            return None
    return None


def _current_limit(tree: exp.Query) -> int | None:
    limit = tree.args.get("limit")
    if isinstance(limit, exp.Limit):
        return _literal_int(limit.expression)
    if isinstance(limit, exp.Fetch):
        return _literal_int(limit.args.get("count"))
    return None


def _visible_ctes(table: exp.Table) -> set[str]:
    """Nomes de CTE que esta referência enxerga, pelas regras de escopo do SQL.

    Dentro do corpo de uma CTE só valem as CTEs declaradas ANTES dela no mesmo WITH (e a própria,
    se for WITH RECURSIVE); no corpo da consulta que tem o WITH valem todas. Resolver pelo escopo,
    e não por um conjunto global de nomes, impede que uma CTE homônima esconda uma tabela real.
    """
    visible: set[str] = set()
    child: exp.Expression = table
    parent = table.parent
    while parent is not None:
        if isinstance(parent, exp.With):
            names = [cte.alias_or_name.lower() for cte in parent.expressions]
            position = next(i for i, cte in enumerate(parent.expressions) if cte is child)
            visible.update(names[:position])
            if parent.args.get("recursive"):
                visible.add(names[position])
        else:
            with_clause = parent.args.get("with_")
            if isinstance(with_clause, exp.With) and child is not with_clause:
                visible.update(cte.alias_or_name.lower() for cte in with_clause.expressions)
        child, parent = parent, parent.parent
    return visible


def _refers_to_cte(table: exp.Table) -> bool:
    """True só se a referência resolve para uma CTE visível, e não para uma tabela real de mesmo nome.

    `WITH tables AS (SELECT * FROM information_schema.tables) SELECT * FROM tables` não pode
    esconder a tabela real da checagem de `allowed_tables`: referência qualificada e referência
    dentro do corpo da própria CTE (sem RECURSIVE) apontam para a tabela real.
    """
    if table.args.get("db") or table.args.get("catalog"):
        return False
    return table.name.lower() in _visible_ctes(table)


@traceable(run_type="tool", name="validate_read_only_sql")
def validate_read_only_sql(
    sql: str,
    dialect: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    allowed_tables: set[str] | None = None,
) -> ValidatedQuery:
    """Aceita só uma consulta de leitura e devolve o SQL normalizado com LIMIT garantido.

    A árvore inteira é percorrida (CTEs, subconsultas, UNIONs), então um DELETE dentro de
    um WITH é barrado como qualquer outro. `allowed_tables` barra tabelas fora do catálogo.
    """
    dialect = check_dialect(dialect)
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except SqlglotError as exc:
        raise UnsafeQueryError(f"SQL inválido para o dialeto {dialect}: {exc}") from exc

    if len(statements) != 1:
        raise UnsafeQueryError(f"Esperada exatamente 1 instrução, recebidas {len(statements)}.")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise UnsafeQueryError(f"Somente SELECT/WITH é permitido; recebido {tree.key.upper()}.")

    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise UnsafeQueryError(f"Operação proibida na consulta: {node.key.upper()}.")
        if isinstance(node, exp.Func) and (forbidden := _function_names(node) & _FORBIDDEN_FUNCTIONS):
            raise UnsafeQueryError(f"Função proibida na consulta: {', '.join(sorted(forbidden))}.")

    for select in tree.find_all(exp.Select):
        bare = [
            j for j in select.args.get("joins") or []
            if not (j.args.get("on") or j.args.get("using") or j.args.get("method"))
        ]  # fmt: skip
        if len(bare) > MAX_BARE_JOINS:
            raise UnsafeQueryError("Muitas tabelas sem condição de JOIN (produto cartesiano).")

    tables: set[str] = set()
    for table in tree.find_all(exp.Table):
        if isinstance(table.this, exp.Func):
            raise UnsafeQueryError("Funções de tabela não são permitidas como fonte de dados.")
        qualifier = [part.lower() for part in (table.catalog, table.db) if part]
        if any(part != "main" for part in qualifier):
            raise UnsafeQueryError("Tabela fora do catálogo: só o schema main é permitido.")
        if table.name and not _refers_to_cte(table):
            tables.add(table.name)

    if forbidden := sorted(t for t in tables if is_forbidden_table(t)):
        raise UnsafeQueryError(f"Tabelas fora do catálogo: {', '.join(forbidden)}.")
    lowered = {t.lower() for t in tables}
    if lowered & SHOP_VIEW_TABLES and lowered & _OLIST_REIDENTIFYING:
        raise UnsafeQueryError("Cruzar as views da loja com customers/geolocation é proibido (reidentificação).")

    if allowed_tables is not None:
        allowed = {name.lower() for name in allowed_tables}
        unknown = sorted(t for t in tables if t.lower() not in allowed)
        if unknown:
            raise UnsafeQueryError(f"Tabelas fora do catálogo: {', '.join(unknown)}.")

    current = _current_limit(tree)
    if current is None or current > max_rows:
        tree = tree.limit(max_rows, dialect=dialect)
        current = max_rows

    return ValidatedQuery(sql=tree.sql(dialect=dialect), dialect=dialect, tables=sorted(tables), row_limit=current)
