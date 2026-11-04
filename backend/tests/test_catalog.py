import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from app.services.catalog import CatalogService


class FakeCollection:
    def __init__(self, rows: list[dict]):
        self.rows = rows

    async def aggregate(self, _pipeline):
        return self

    async def to_list(self, length=None):
        return self.rows


class FakeDatabase:
    name = "olist_test"

    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def __getitem__(self, table_name):
        return FakeCollection(self.tables[table_name])


def _column(name: str, data_type: str) -> dict:
    return {"column_name": name, "data_type": data_type, "description": "d", "semantic_role": "r", "confidence": "high"}


class CountingFakeLLM(FakeListChatModel):
    canned: dict = {}
    calls: dict = {}

    def with_structured_output(self, schema, **kw):
        def respond(_msgs):
            self.calls[schema.__name__] = self.calls.get(schema.__name__, 0) + 1
            return schema.model_validate(self.canned[schema.__name__])

        return RunnableLambda(respond)


@pytest.fixture
def db():
    # Mesmas colunas nas duas tabelas de propósito: o fake LLM devolve a mesma resposta
    # para qualquer entrada, e _check_column_coverage (prompts.py) exige que os nomes
    # recebidos batam exatamente com os da amostra.
    return FakeDatabase(
        {
            "orders": [{"id": "a1", "value": 10.0}, {"id": "a2", "value": 20.0}],
            "products": [{"id": "p1", "value": 5.0}],
        }
    )


@pytest.fixture
def llm():
    return CountingFakeLLM(
        responses=["x"],
        canned={
            "ColumnMetadataOutput": {
                "table_name": "t",
                "columns": [_column("id", "string"), _column("value", "double")],
            },
            "TableDescriptionOutput": {
                "table_name": "t",
                "description": "Pedidos",
                "business_domain": "vendas",
                "information_type": "transação",
                "granularity": "um por pedido",
                "analytical_use_cases": ["receita"],
            },
        },
    )


def test_get_builds_and_caches_per_table(db, llm):
    service = CatalogService(db, llm, known_tables={"orders", "products"})

    async def run():
        first = await service.get(["orders"])
        second = await service.get(["orders"])
        return first, second

    first, second = asyncio.run(run())

    assert first[0].table_name == "orders"
    assert first == second
    # A segunda chamada usou o cache: nenhuma chamada extra ao LLM.
    assert llm.calls["ColumnMetadataOutput"] == 1
    assert llm.calls["TableDescriptionOutput"] == 1


def test_get_without_args_returns_all_known_tables(db, llm):
    service = CatalogService(db, llm, known_tables={"orders", "products"})

    result = asyncio.run(service.get())

    assert {t.table_name for t in result} == {"orders", "products"}


def test_invalidate_forces_rebuild(db, llm):
    service = CatalogService(db, llm, known_tables={"orders"})
    asyncio.run(service.get(["orders"]))

    service.invalidate("orders")
    asyncio.run(service.get(["orders"]))

    assert llm.calls["ColumnMetadataOutput"] == 2


def test_unknown_table_is_ignored(db, llm):
    service = CatalogService(db, llm, known_tables={"orders"})

    result = asyncio.run(service.get(["tabela_fantasma"]))

    assert result == []
