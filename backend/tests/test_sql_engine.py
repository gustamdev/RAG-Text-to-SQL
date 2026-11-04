import asyncio

import duckdb
import pytest

from app.database.sql_engine import SQLEngine
from app.prompts import SQLAgentOutput
from app.schemas.query import QueryRequest
from app.services.query_runner import QueryRunner


@pytest.fixture
def engine(tmp_path):
    path = tmp_path / "test.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE orders AS SELECT i AS order_id, i % 3 AS status FROM range(10) t(i)")
        con.execute("CREATE TABLE nums AS SELECT i AS n FROM range(5000) t(i)")
    engine = SQLEngine(path, timeout_s=5, max_concurrent=2)
    engine.open()
    yield engine
    engine.close()


@pytest.fixture
def runner(engine):
    return QueryRunner(engine, ttl_s=60, max_results=10)


def run(runner: QueryRunner, sql: str, max_rows: int = 100):
    return asyncio.run(runner.execute(QueryRequest(sql=sql, max_rows=max_rows)))


def test_select_succeeds(runner):
    result = run(runner, "select status, count(*) as total from orders group by status order by status")

    assert result.status == "succeeded"
    assert result.columns == ["status", "total"]
    assert result.rows == [[0, 4], [1, 3], [2, 3]]
    assert result.row_count == 3
    assert not result.truncated


@pytest.mark.parametrize(
    "sql",
    [
        "delete from orders",
        "drop table orders",
        "select 1; delete from orders",
        "with d as (delete from orders returning *) select * from d",
        "select * from read_csv('/etc/passwd')",
        "select * from information_schema.tables",
        "attach 'x.db' as y",
    ],
)
def test_unsafe_sql_is_rejected(runner, sql):
    result = run(runner, sql)

    assert result.status == "rejected"
    assert result.error
    assert result.rows == []


def test_unknown_column_is_sql_error(runner):
    result = run(runner, "select nao_existe from orders")

    assert result.status == "sql_error"
    assert "\n" not in result.error


def test_rows_are_truncated_at_max_rows(runner):
    result = run(runner, "select order_id from orders", max_rows=4)

    assert result.status == "succeeded"
    assert result.row_count == 4
    assert result.truncated


def test_explicit_limit_within_max_rows_is_not_truncated(runner):
    result = run(runner, "select order_id from orders limit 4", max_rows=4)

    assert result.row_count == 4
    assert not result.truncated


def test_slow_query_times_out(engine):
    # O timeout entra na config da conexão, então precisa reabrir.
    engine.close()
    engine.timeout_s = 0.2
    engine.open()
    runner = QueryRunner(engine, ttl_s=60, max_results=10)

    result = run(runner, "select sum(a.n * b.n * c.n) from nums a, nums b, nums c")

    assert result.status == "timeout"


def test_closed_engine_is_unavailable(engine, runner):
    engine.close()

    assert run(runner, "select order_id from orders").status == "unavailable"


def test_submit_then_get(runner):
    async def flow():
        pending = runner.submit(QueryRequest(sql="select count(*) as total from orders"))
        assert pending.status == "pending"
        await asyncio.gather(*runner._tasks)
        return pending.query_id, runner.get(pending.query_id)

    query_id, result = asyncio.run(flow())

    assert result.query_id == query_id
    assert result.status == "succeeded"
    assert result.rows == [[10]]
    assert runner.get("desconhecido") is None


def test_from_agent_only_accepts_generated_sql():
    clarify = SQLAgentOutput(status="needs_clarification", explanation="ambígua", clarification_questions=["?"])
    ok = SQLAgentOutput(status="ok", sql="select 1", explanation="e")

    assert QueryRequest.from_agent(clarify) is None
    assert QueryRequest.from_agent(ok).sql == "select 1"
