"""Catálogo de metadados: gera e guarda em memória a `TableMetadata` de cada tabela.

Sem isso, o PROMPT_OPTIMIZER e o SQL_AGENT (prompts.py) não têm schema para trabalhar — os
dois exigem `catalog: list[TableMetadata]`, e nada no projeto ainda produzia essa lista.

A geração chama LLM (COLUMN_METADATA + TABLE_DESCRIPTION) e amostra o Mongo, então é cara:
acontece uma vez por tabela, na primeira pergunta que precisar dela, e o resultado fica
guardado aqui. Sem TTL de propósito — o schema do Olist é fixo; para atualizar, reinicie o
processo ou chame `invalidate()`.
"""

import asyncio
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langsmith import traceable
from pymongo.asynchronous.database import AsyncDatabase

from app.prompts import (
    COLUMN_METADATA,
    TABLE_DESCRIPTION,
    ColumnMetadataInput,
    TableDescriptionInput,
    TableMetadata,
    sample_table,
    sample_table_duckdb,
)
from app.sql_guard import SHOP_VIEW_TABLES, is_forbidden_table

logger = logging.getLogger(__name__)


class CatalogService:
    def __init__(self, db: AsyncDatabase, llm: BaseChatModel, *, known_tables: set[str], engine: Any = None):
        self.db = db
        self.llm = llm
        # Com `engine`, a amostra vem do DuckDB projetado (E7); sem ele, do Mongo (só tabelas não-`shop_*`).
        self.engine = engine
        self.known_tables = {name for name in known_tables if not is_forbidden_table(name)}
        self._cache: dict[str, TableMetadata] = {}
        # Uma trava por tabela (criada sob demanda): duas perguntas simultâneas sobre "orders" não
        # geram o metadado em dobro, mas uma sobre "orders" e outra sobre "products" não se bloqueiam.
        self._locks: dict[str, asyncio.Lock] = {}

    def update_tables(self, tables: set[str]) -> None:
        """Chamado após cada rebuild do snapshot: aceita tabelas novas e refaz o metadado das views da loja."""
        self.known_tables = {name for name in tables if not is_forbidden_table(name)}
        for name in SHOP_VIEW_TABLES:
            self.invalidate(name)

    async def get(self, table_names: list[str] | None = None) -> list[TableMetadata]:
        """Catálogo das tabelas pedidas (ou de todas, se omitido), gerando o que faltar no cache."""
        wanted = [name for name in (table_names or sorted(self.known_tables)) if name in self.known_tables]
        missing = [name for name in wanted if name not in self._cache]
        if missing:
            # Tabelas diferentes podem ser amostradas e descritas em paralelo; a trava por
            # tabela só serializa chamadas concorrentes para a MESMA tabela.
            await asyncio.gather(*(self._build(name) for name in missing))
        return [self._cache[name] for name in wanted]

    def invalidate(self, table_name: str | None = None) -> None:
        if table_name is None:
            self._cache.clear()
        else:
            self._cache.pop(table_name, None)

    @traceable(
        run_type="chain",
        name="catalog_build_table",
        process_inputs=lambda inputs: {k: v for k, v in inputs.items() if k != "self"},
    )
    async def _build(self, table_name: str) -> None:
        async with self._locks.setdefault(table_name, asyncio.Lock()):
            if table_name in self._cache:  # outra chamada já construiu enquanto esperávamos a trava
                return
            logger.info("Gerando metadados de %s (amostra + LLM)...", table_name)
            sample = (
                await sample_table_duckdb(self.engine, table_name)
                if self.engine is not None
                else await sample_table(self.db, table_name)
            )
            columns = await COLUMN_METADATA.chain(self.llm).ainvoke(ColumnMetadataInput(table=sample))
            other_tables = sorted(self.known_tables - {table_name})
            description = await TABLE_DESCRIPTION.chain(self.llm).ainvoke(
                TableDescriptionInput(table=sample, column_metadata=columns, other_tables=other_tables)
            )
            self._cache[table_name] = TableMetadata(
                schema_name=sample.schema_name,
                table_name=table_name,
                description=description,
                columns=columns.columns,
            )
