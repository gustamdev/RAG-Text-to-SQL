"""Executa SQL no motor: valida, roda e guarda o resultado para consulta posterior.

`submit` + `get` atendem o par POST (dispara) / GET (busca resultado); `execute` serve
para quem quer esperar o resultado direto, como um nó de agente.

O store é um dict em memória: cada worker do uvicorn tem o seu. Com mais de um worker,
o GET pode cair num processo que não conhece o id; aí o store precisa ir para Redis.
"""

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

import duckdb
from langsmith import traceable

from app.database.sql_engine import DIALECT, EngineUnavailable, QueryTimeout, SQLEngine
from app.prompts import UnsafeQueryError, validate_read_only_sql
from app.schemas.query import QueryRequest, QueryResult, QueryStatus

logger = logging.getLogger(__name__)

MAX_ERROR_CHARS = 300


def _short_error(exc: Exception) -> str:
    # Só a primeira linha: o DuckDB às vezes anexa trechos da query e sugestões em linhas seguintes,
    # e esse texto volta para o LLM numa nova tentativa.
    first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return first_line[:MAX_ERROR_CHARS]


class QueryRunner:
    def __init__(self, engine: SQLEngine, *, ttl_s: float, max_results: int):
        self.engine = engine
        self.ttl_s = ttl_s
        self.max_results = max_results
        self._results: dict[str, tuple[float, QueryResult]] = {}
        # Referência forte às tasks: sem isso o event loop pode coletá-las no meio da execução.
        self._tasks: set[asyncio.Task] = set()

    @traceable(
        run_type="tool",
        name="query_runner_execute",
        process_inputs=lambda inputs: {k: v for k, v in inputs.items() if k != "self"},
        # Sem as linhas: um resultado de até 500 linhas só pesa o trace sem ajudar a depurar.
        process_outputs=lambda result: {
            "status": result.status,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "error": result.error,
        },
    )
    async def execute(self, request: QueryRequest, *, query_id: str | None = None) -> QueryResult:
        query_id = query_id or uuid.uuid4().hex
        created_at = datetime.now(UTC)
        started = time.perf_counter()

        def finish(status: QueryStatus, sql: str, error: str | None = None, **data) -> QueryResult:
            return QueryResult.model_construct(
                query_id=query_id,
                status=status,
                sql=sql,
                columns=data.get("columns", []),
                rows=data.get("rows", []),
                row_count=len(data.get("rows", [])),
                truncated=data.get("truncated", False),
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                error=error,
                created_at=created_at,
                finished_at=datetime.now(UTC),
            )

        if not self.engine.available:
            return finish("unavailable", request.sql, "Motor SQL indisponível.")

        try:
            # +1 no LIMIT imposto: é a linha extra que o fetchmany usa para saber se truncou.
            validated = validate_read_only_sql(
                request.sql, DIALECT, max_rows=request.max_rows + 1, allowed_tables=self.engine.tables
            )
        except UnsafeQueryError as exc:
            logger.warning("Consulta rejeitada (%s): %.200s", exc, request.sql)
            return finish("rejected", request.sql, _short_error(exc))

        try:
            columns, rows, truncated = await self.engine.run(validated.sql, request.max_rows)
        except EngineUnavailable as exc:
            return finish("unavailable", validated.sql, _short_error(exc))
        except QueryTimeout as exc:
            return finish("timeout", validated.sql, _short_error(exc))
        except duckdb.Error as exc:
            return finish("sql_error", validated.sql, _short_error(exc))

        return finish(
            "succeeded", validated.sql, columns=columns, rows=[list(row) for row in rows], truncated=truncated
        )

    def submit(self, request: QueryRequest) -> QueryResult:
        """Registra a consulta, dispara em segundo plano e devolve o resultado 'pending' com o id."""
        self._evict()
        query_id = uuid.uuid4().hex
        pending = QueryResult.model_construct(
            query_id=query_id,
            status="pending",
            sql=request.sql,
            columns=[],
            rows=[],
            row_count=0,
            truncated=False,
            elapsed_ms=None,
            error=None,
            created_at=datetime.now(UTC),
            finished_at=None,
        )
        self._store(pending)

        task = asyncio.create_task(self._run_and_store(request, pending))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return pending

    def get(self, query_id: str) -> QueryResult | None:
        self._evict()
        entry = self._results.get(query_id)
        return entry[1] if entry else None

    async def _run_and_store(self, request: QueryRequest, pending: QueryResult) -> None:
        self._store(pending.model_copy(update={"status": "running"}))
        try:
            result = await self.execute(request, query_id=pending.query_id)
        except Exception as exc:  # a task roda solta: erro não tratado sumiria sem deixar resultado
            logger.exception("Falha inesperada na consulta %s", pending.query_id)
            result = pending.model_copy(
                update={"status": "sql_error", "error": _short_error(exc), "finished_at": datetime.now(UTC)}
            )
        self._store(result.model_copy(update={"created_at": pending.created_at}))

    def _store(self, result: QueryResult) -> None:
        self._results[result.query_id] = (time.monotonic(), result)

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [qid for qid, (stored_at, _) in self._results.items() if now - stored_at > self.ttl_s]
        for qid in expired:
            del self._results[qid]
        # Reatribuir uma chave não muda sua posição no dict, então o mais antigo sai pelo horário gravado.
        overflow = len(self._results) - self.max_results
        if overflow > 0:
            oldest = sorted(self._results, key=lambda qid: self._results[qid][0])[:overflow]
            for qid in oldest:
                del self._results[qid]
