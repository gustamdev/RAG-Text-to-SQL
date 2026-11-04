"""Guarda de regressão: o catálogo mostrado ao LLM precisa usar os mesmos nomes de campo que
ele tem que devolver, ou _ground_optimizer_output descarta tabelas reais silenciosamente
(visto em produção: "schema.tabela" ecoado de volta em table_name não batia com o catálogo)."""

from app.prompts import (
    ColumnDescription,
    PromptOptimizerInput,
    PromptOptimizerOutput,
    RelevantColumn,
    RelevantTable,
    TableDescriptionOutput,
    TableMetadata,
    _catalog_payload,
    _ground_optimizer_output,
)


def _column(name: str) -> ColumnDescription:
    return ColumnDescription(
        column_name=name, data_type="string", description="d", semantic_role="r", confidence="high"
    )


CATALOG = [
    TableMetadata(
        schema_name="olist",
        table_name="customers",
        description=TableDescriptionOutput(
            table_name="customers",
            description="Clientes",
            business_domain="vendas",
            information_type="cadastro",
            granularity="um por cliente",
            analytical_use_cases=["contagem de clientes"],
        ),
        columns=[_column("customer_id")],
    )
]


def test_catalog_payload_exposes_bare_table_name_not_schema_prefixed():
    payload = _catalog_payload(CATALOG)[0]

    assert payload["schema_name"] == "olist"
    assert payload["table_name"] == "customers"
    assert "table" not in payload  # a chave antiga, ambígua ("schema.tabela" numa string só)


def _optimizer_output(table_name: str) -> PromptOptimizerOutput:
    return PromptOptimizerOutput(
        original_question="q",
        interpreted_intent="i",
        relevant_tables=[RelevantTable(table_name=table_name, justification="j")],
        relevant_columns=[RelevantColumn(table_name=table_name, column_name="customer_id", meaning="m", usage="select")],
        filters=[],
        metrics_and_aggregations=[],
        grouping_and_ordering=[],
        query_plan=["p"],
        ambiguities=[],
        missing_information=[],
        sql_context="ctx",
    )


def test_ground_optimizer_output_keeps_table_when_name_matches_catalog():
    inp = PromptOptimizerInput(question="q", catalog=CATALOG, sql_dialect="duckdb")

    grounded = _ground_optimizer_output(inp, _optimizer_output("customers"))

    assert [t.table_name for t in grounded.relevant_tables] == ["customers"]
    assert [c.column_name for c in grounded.relevant_columns] == ["customer_id"]


def test_ground_optimizer_output_drops_schema_prefixed_table_name():
    # Reproduz o bug: o modelo ecoa "olist.customers" (como via na chave antiga do payload)
    # em vez de "customers" — o nome não bate com o catálogo e a tabela é descartada.
    inp = PromptOptimizerInput(question="q", catalog=CATALOG, sql_dialect="duckdb")

    grounded = _ground_optimizer_output(inp, _optimizer_output("olist.customers"))

    assert grounded.relevant_tables == []
    assert grounded.relevant_columns == []
