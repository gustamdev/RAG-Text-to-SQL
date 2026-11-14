"""Motor SQL: snapshot DuckDB das coleções do Mongo, aberto somente leitura.

O Mongo continua sendo a fonte. O DuckDB é uma cópia analítica que existe só para o
SQL gerado pelos agentes ter onde rodar, e para as consultas fixas da vitrine e do backoffice
(`database/analytics.py`). Este módulo não valida SQL: o SQL de agente passa por
`validate_read_only_sql` (`services/query_runner.py`); o SQL fixo é constante do código, e
qualquer valor variável entra por `params` (placeholders), nunca por interpolação.
"""

import asyncio
import logging
import os
import shutil
import threading
import time
from collections.abc import Sequence
from itertools import batched
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from langsmith import traceable
from pymongo import MongoClient

from app.config import settings
from app.database.seed_mongo import CSV_FILES
from app.database.shop_views import write_shop_views

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


_BUILD_LOCK = (
    threading.Lock()
)  # dois builds no mesmo .tmp se corromperiam; o single-flight real fica em services/snapshot.py
BATCH_SIZE = 5000


def build_snapshot(client: MongoClient, path: Path) -> bool:
    """Copia as coleções do Olist e as views da loja (sem PII) para um arquivo DuckDB.

    Retorna False se o Mongo estiver vazio. Lê o Mongo em lotes e troca o arquivo de forma atômica.
    """
    db = client[settings.MONGO_DB_NAME]
    if db["orders"].estimated_document_count() == 0:
        logger.warning("Mongo sem pedidos: snapshot DuckDB não gerado, motor SQL ficará indisponível.")
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with _BUILD_LOCK:
        tmp_path.unlink(missing_ok=True)
        # Escreve num arquivo temporário e troca no fim: um build interrompido nunca deixa
        # um snapshot pela metade no lugar do bom.
        try:
            with duckdb.connect(str(tmp_path)) as con:
                for collection in CSV_FILES:
                    _copy_collection(con, db[collection], collection)
                counts = write_shop_views(db, con)
            os.chmod(tmp_path, 0o600)  # snapshot é dado pessoal pseudonimizado
            os.replace(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)
            tmp_path.with_name(f"{tmp_path.name}.wal").unlink(missing_ok=True)
    logger.info("Snapshot DuckDB gerado em %s (loja: %s)", path, counts)
    return True


def _copy_collection(con: duckdb.DuckDBPyConnection, collection: Any, name: str) -> None:
    total = 0
    for batch in batched(collection.find({}, {"_id": 0}), BATCH_SIZE, strict=False):
        frame = pd.DataFrame(list(batch)).convert_dtypes()
        con.register("frame", frame)
        # shortcut: tipos vêm do 1º lote; coluna toda nula nele ficaria sem tipo certo. Subir BATCH_SIZE se acontecer.
        verb = "INSERT INTO" if total else "CREATE TABLE"
        con.execute(f'{verb} "{name}" ' + ("SELECT * FROM frame" if total else "AS SELECT * FROM frame"))
        con.unregister("frame")
        total += len(frame)
    logger.info("  snapshot %-35s %7d linhas", name, total)


class SQLEngine:
    def __init__(self, path: Path, *, timeout_s: float, max_concurrent: int):
        self.path = path
        self.timeout_s = timeout_s
        self.tables: set[str] = set()
        self._con: duckdb.DuckDBPyConnection | None = None
        self._live: Path | None = None
        self._generation = 0
        self._inflight: dict[int, int] = {}  # consultas em andamento por conexão (id)
        self._slots = asyncio.Semaphore(max_concurrent)

    @property
    def available(self) -> bool:
        return self._con is not None

    def _connect(self) -> tuple[duckdb.DuckDBPyConnection, set[str], Path]:
        # O DuckDB reaproveita a instância aberta para o MESMO caminho (ignora o arquivo trocado por
        # os.replace). Cada geração abre um hardlink próprio, o que força uma instância nova.
        self._generation += 1
        live = self.path.with_name(f"{self.path.name}.live{os.getpid()}.{self._generation}")
        live.unlink(missing_ok=True)
        try:
            os.link(self.path, live)
        except OSError:
            shutil.copyfile(self.path, live)
        try:
            # Timeout nativo do DuckDB, travado pelo lock_configuration. Cancelar de fora com
            # cursor.interrupt() não serve: o DuckDB 2 recusa a chamada enquanto o cursor está ocupado.
            config = _READ_ONLY_CONFIG | {"max_execution_time": int(self.timeout_s * 1000)}
            con = duckdb.connect(str(live), read_only=True, config=config)
            rows = con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        except Exception:
            live.unlink(missing_ok=True)
            raise
        return con, {name for (name,) in rows}, live

    def open(self) -> None:
        self._con, self.tables, self._live = self._connect()
        logger.info("Motor SQL aberto (%d tabelas, somente leitura)", len(self.tables))

    async def reload(self) -> None:
        """Passa a ler o arquivo novo sem derrubar consultas em voo: abre, troca a referência e só
        fecha a conexão antiga depois que as consultas dela terminarem."""
        new_con, tables, live = await asyncio.to_thread(self._connect)
        old_con, old_live = self._con, self._live
        self._con, self.tables, self._live = new_con, tables, live
        logger.info("Motor SQL recarregado (%d tabelas)", len(tables))
        if old_con is None:
            return
        deadline = time.monotonic() + self.timeout_s + 5  # max_execution_time já limita cada consulta
        while self._inflight.get(id(old_con)) and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        self._inflight.pop(id(old_con), None)
        old_con.close()
        if old_live is not None:
            old_live.unlink(missing_ok=True)

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None
            self.tables = set()
        if self._live is not None:
            self._live.unlink(missing_ok=True)
            self._live = None

    @traceable(
        run_type="tool",
        name="duckdb_execute",
        process_inputs=lambda inputs: {k: v for k, v in inputs.items() if k != "self"},
    )
    async def run(
        self, sql: str, max_rows: int, params: Sequence[Any] | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]], bool]:
        """Executa uma consulta JÁ validada (ou constante do código). Retorna (colunas, linhas, truncado).

        `params` são os valores dos placeholders `?` do SQL.
        """
        if self._con is None:
            raise EngineUnavailable("Motor SQL indisponível.")

        async with self._slots:
            con = self._con  # lido sem await até o contador subir: reload() não fecha esta conexão antes de zerar
            if con is None:
                raise EngineUnavailable("Motor SQL indisponível.")
            key = id(con)
            self._inflight[key] = self._inflight.get(key, 0) + 1
            try:
                # Um cursor por consulta: a conexão DuckDB não é segura para uso concorrente entre threads.
                cursor = con.cursor()
                try:
                    return await asyncio.to_thread(self._fetch, cursor, sql, max_rows, params)
                except duckdb.InterruptException as exc:
                    raise QueryTimeout(f"Consulta excedeu {self.timeout_s:g}s.") from exc
                finally:
                    cursor.close()
            finally:
                self._inflight[key] -= 1

    @staticmethod
    def _fetch(
        cursor: duckdb.DuckDBPyConnection, sql: str, max_rows: int, params: Sequence[Any] | None = None
    ) -> tuple[list[str], list[tuple[Any, ...]], bool]:
        cursor.execute(sql, params or [])
        columns = [column[0] for column in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
        return columns, rows[:max_rows], len(rows) > max_rows
