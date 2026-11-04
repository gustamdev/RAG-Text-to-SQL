"""Motor SQL: snapshot DuckDB das coleções do Mongo, aberto somente leitura.

O Mongo continua sendo a fonte. O DuckDB é uma cópia analítica que existe só para o
SQL gerado pelos agentes ter onde rodar. Este módulo não valida SQL: quem chama
(`services/query_runner.py`) passa tudo por `validate_read_only_sql` antes.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from langsmith import traceable
from pymongo import MongoClient

from app.config import settings
from app.database.seed_mongo import CSV_FILES

logger = logging.getLogger(__name__)

DIALECT = "duckdb"

# Defesa no próprio banco, independente do validador: sem leitura de arquivo/rede
# (read_csv, ATTACH, COPY), sem baixar extensões e sem SET para desfazer isso.
_READ_ONLY_CONFIG = {
    "enable_external_access": False,
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "lock_configuration": True,
}


class EngineUnavailable(RuntimeError):
    pass


class QueryTimeout(TimeoutError):
    pass


def build_snapshot(client: MongoClient, path: Path) -> bool:
    """Copia as coleções do Olist para um arquivo DuckDB. Retorna False se o Mongo estiver vazio."""
    db = client[settings.MONGO_DB_NAME]
    if db["orders"].estimated_document_count() == 0:
        logger.warning("Mongo sem pedidos: snapshot DuckDB não gerado, motor SQL ficará indisponível.")
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.unlink(missing_ok=True)

    # Escreve num arquivo temporário e troca no fim: um build interrompido nunca deixa
    # um snapshot pela metade no lugar do bom.
    with duckdb.connect(str(tmp_path)) as con:
        for collection in CSV_FILES:
            frame = pd.DataFrame(list(db[collection].find({}, {"_id": 0}))).convert_dtypes()
            con.register("frame", frame)
            con.execute(f'CREATE TABLE "{collection}" AS SELECT * FROM frame')
            con.unregister("frame")
            logger.info("  snapshot %-35s %7d linhas", collection, len(frame))
    os.replace(tmp_path, path)
    logger.info("Snapshot DuckDB gerado em %s", path)
    return True


class SQLEngine:
    def __init__(self, path: Path, *, timeout_s: float, max_concurrent: int):
        self.path = path
        self.timeout_s = timeout_s
        self.tables: set[str] = set()
        self._con: duckdb.DuckDBPyConnection | None = None
        self._slots = asyncio.Semaphore(max_concurrent)

    @property
    def available(self) -> bool:
        return self._con is not None

    def open(self) -> None:
        # Timeout nativo do DuckDB, travado pelo lock_configuration. Cancelar de fora com
        # cursor.interrupt() não serve: o DuckDB 2 recusa a chamada enquanto o cursor está ocupado.
        config = _READ_ONLY_CONFIG | {"max_execution_time": int(self.timeout_s * 1000)}
        self._con = duckdb.connect(str(self.path), read_only=True, config=config)
        rows = self._con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        self.tables = {name for (name,) in rows}
        logger.info("Motor SQL aberto (%d tabelas, somente leitura)", len(self.tables))

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None
            self.tables = set()

    @traceable(
        run_type="tool",
        name="duckdb_execute",
        process_inputs=lambda inputs: {k: v for k, v in inputs.items() if k != "self"},
    )
    async def run(self, sql: str, max_rows: int) -> tuple[list[str], list[tuple[Any, ...]], bool]:
        """Executa uma consulta JÁ validada. Retorna (colunas, linhas, truncado)."""
        if self._con is None:
            raise EngineUnavailable("Motor SQL indisponível.")

        async with self._slots:
            # Um cursor por consulta: a conexão DuckDB não é segura para uso concorrente entre threads.
            cursor = self._con.cursor()
            try:
                return await asyncio.to_thread(self._fetch, cursor, sql, max_rows)
            except duckdb.InterruptException as exc:
                raise QueryTimeout(f"Consulta excedeu {self.timeout_s:g}s.") from exc
            finally:
                cursor.close()

    @staticmethod
    def _fetch(
        cursor: duckdb.DuckDBPyConnection, sql: str, max_rows: int
    ) -> tuple[list[str], list[tuple[Any, ...]], bool]:
        cursor.execute(sql)
        columns = [column[0] for column in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
        return columns, rows[:max_rows], len(rows) > max_rows
