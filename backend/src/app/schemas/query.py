from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.prompts import SQLAgentOutput
from app.sql_guard import DEFAULT_MAX_ROWS, MAX_ROWS_CAP

# pending/running: em andamento. Os demais são finais; rejected, sql_error e timeout
# dão ao agente motivo para gerar de novo, unavailable pede só reenvio.
QueryStatus = Literal["pending", "running", "succeeded", "rejected", "sql_error", "timeout", "unavailable"]


class QueryRequest(BaseModel):
    sql: str = Field(min_length=1)
    max_rows: int = Field(default=DEFAULT_MAX_ROWS, ge=1, le=MAX_ROWS_CAP)
    question: str | None = None

    @classmethod
    def from_agent(cls, output: SQLAgentOutput, *, max_rows: int = DEFAULT_MAX_ROWS) -> "QueryRequest | None":
        """None quando o agente não gerou SQL (pediu esclarecimento ou não tinha como responder)."""
        if output.status != "ok" or not output.sql:
            return None
        return cls(sql=output.sql, max_rows=max_rows)


class QueryResult(BaseModel):
    """Montado pelo motor via model_construct: os dados vêm do nosso banco, não de fora."""

    query_id: str
    status: QueryStatus
    sql: str
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False
    elapsed_ms: float | None = None
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
