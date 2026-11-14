"""E7: o agente enxerga os dados vivos da loja (views sem PII), sem LLM e sem Mongo/DuckDB reais."""

import asyncio
import json
import stat
import time
from datetime import datetime

import duckdb
import mongomock
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from app.config import settings
from app.core.pii import REDACTED, redact
from app.database.golden_shop import SHOP_GOLDEN
from app.database.shop_views import VIEW_COLUMNS
from app.database.sql_engine import SQLEngine, build_snapshot
from app.prompts import sample_table
from app.services.catalog import CatalogService
from app.services.memory import MemoryService
from app.services.snapshot import SnapshotService
from app.sql_guard import SHOP_VIEW_TABLES, UnsafeQueryError, validate_read_only_sql

PII_TEXT = ["Ana Souza", "ana@exemplo.com", "Anita", "Av. Paulista", "Bela Vista", "01310100", "01310-100", "4242"]


def _mongo() -> mongomock.MongoClient:
    client = mongomock.MongoClient()
    db = client[settings.MONGO_DB_NAME]
    db["orders"].insert_one({"order_id": "o1", "order_status": "delivered"})  # só para o build não abortar
    db["shop_customers"].insert_many(
        [
            {
                "_id": "c1",
                "email": "ana@exemplo.com",
                "nickname": "Anita",
                "email_verified": True,
                "deleted_at": None,
                "created_at": datetime(2026, 11, 1, 10, 30),
                "last_login_at": datetime(2026, 11, 2, 8, 0),
            },
            {
                "_id": "c2",
                "email": "gone@exemplo.com",
                "nickname": "Gone",
                "email_verified": True,
                "deleted_at": datetime(2026, 11, 5),
                "created_at": datetime(2026, 11, 1),
            },
        ]
    )
    db["shop_addresses"].insert_one(
        {
            "customer_id": "c1",
            "recipient": "Ana Souza",
            "zip": "01310100",
            "street": "Av. Paulista",
            "number": "1000",
            "district": "Bela Vista",
            "city": "São Paulo",
            "state": "SP",
            "is_default": True,
        }
    )
    return client


def _order(order_id: str, customer_id: str | None, state: str = "paid", total: int = 19820) -> dict:
    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "state": state,
        "items": [
            {
                "product_id": "p1",
                "title": "Anita Modelo",
                "category": "cama_mesa_banho",
                "qty": 2,
                "unit_price_cents": 8990,
                "line_total_cents": 17980,
            }
        ],
        "subtotal_cents": 17980,
        "freight_cents": 1840,
        "discount_cents": 0,
        "total_cents": total,
        "shipping": {"option": "standard", "label": "Padrão", "days_min": 4, "days_max": 6},
        "address": {
            "recipient": "Ana Souza",
            "zip": "01310100",
            "street": "Av. Paulista",
            "number": "1000",
            "district": "Bela Vista",
            "city": "São Paulo",
            "state": "SP",
        },
        "created_at": datetime(2026, 11, 13, 18, 20),
    }


def _seed_orders(client) -> None:
    db = client[settings.MONGO_DB_NAME]
    db["shop_orders"].insert_many([_order("a" * 32, "c1"), _order("b" * 32, "c2", "refused"), _order("c" * 32, None)])
    db["shop_payments"].insert_one(
        {
            "payment_id": "pay1",
            "order_id": "a" * 32,
            "customer_id": "c1",
            "status": "approved",
            "brand": "visa",
            "last4": "4242",
            "amount_cents": 19820,
            "created_at": datetime(2026, 11, 13, 18, 21),
        }
    )


@pytest.fixture
def mongo():
    client = _mongo()
    _seed_orders(client)
    return client


@pytest.fixture
def engine(tmp_path, mongo):
    path = tmp_path / "snap.duckdb"
    assert build_snapshot(mongo, path)
    eng = SQLEngine(path, timeout_s=30, max_concurrent=4)
    eng.open()
    yield eng
    eng.close()


def _rows(engine, sql: str):
    return asyncio.run(engine.run(sql, 100))[1]


def test_views_have_only_allowlisted_columns_and_no_pii(engine):
    for table, allowed in VIEW_COLUMNS.items():
        columns, rows, _ = asyncio.run(engine.run(f"select * from {table}", 100))
        assert columns == list(allowed)
        assert rows
        dump = json.dumps(rows, default=str)
        assert "@" not in dump
        for text in PII_TEXT:
            assert text not in dump
    forbidden = ("name", "nick", "email", "mail", "street", "address", "last4", "recipient", "phone", "cpf")
    assert not [c for cols in VIEW_COLUMNS.values() for c in cols if any(f in c for f in forbidden)]
    assert set(VIEW_COLUMNS) == SHOP_VIEW_TABLES


def test_view_values_are_projected(engine):
    (order,) = _rows(engine, "select * from shop_orders_view where order_id = '" + "a" * 32 + "'")
    cols = list(VIEW_COLUMNS["shop_orders_view"])
    row = dict(zip(cols, order, strict=True))
    assert row["destination_zip3"] == "013" and row["destination_state"] == "SP"
    assert str(row["order_date"]) == "2026-11-13" and row["items_qty"] == 2
    assert len(row["customer_pseudo"]) == 32 and row["customer_pseudo"] != "c1"
    (payment,) = _rows(engine, "select card_brand, amount_cents from shop_payments_view")
    assert payment == ("visa", 19820)


def test_deleted_customer_absent_after_refresh(tmp_path, mongo):
    path = tmp_path / "s.duckdb"
    build_snapshot(mongo, path)
    with duckdb.connect(str(path), read_only=True) as con:
        assert con.execute("select count(*) from shop_customers_view").fetchone() == (1,)
        # pedido do cliente apagado (logicamente) perde o pseudônimo; o do ativo mantém
        rows = dict(con.execute("select order_id, customer_pseudo from shop_orders_view").fetchall())
    assert rows["b" * 32] is None and rows["c" * 32] is None and rows["a" * 32]
    # apagar também o c1 e refazer: some do agente
    mongo[settings.MONGO_DB_NAME]["shop_customers"].update_one(
        {"_id": "c1"}, {"$set": {"deleted_at": datetime(2026, 11, 14)}}
    )
    build_snapshot(mongo, path)
    with duckdb.connect(str(path), read_only=True) as con:
        assert con.execute("select count(*) from shop_customers_view").fetchone() == (0,)
        assert con.execute("select count(*) from shop_orders_view where customer_pseudo is not null").fetchone() == (0,)


def test_snapshot_file_is_0600(tmp_path, mongo):
    path = tmp_path / "s.duckdb"
    build_snapshot(mongo, path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp*"))


def test_new_order_visible_to_agent_after_rebuild(tmp_path, mongo, engine):
    assert _rows(engine, "select count(*) from shop_orders_view") == [(3,)]
    mongo[settings.MONGO_DB_NAME]["shop_orders"].insert_one(_order("d" * 32, "c1"))
    build_snapshot(mongo, engine.path)
    assert _rows(engine, "select count(*) from shop_orders_view") == [(3,)]  # ainda o arquivo antigo
    asyncio.run(engine.reload())
    assert _rows(engine, "select count(*) from shop_orders_view") == [(4,)]
    assert {"shop_orders_view", "orders"} <= engine.tables


def test_in_flight_query_survives_swap(tmp_path, mongo, engine):
    slow = "select count(*) from range(300000000) t(i) where hash(i) % 7 = 0"

    async def scenario():
        old_con = engine._con
        task = asyncio.create_task(engine.run(slow, 10))
        while not engine._inflight.get(id(old_con)):
            await asyncio.sleep(0.01)
        build_snapshot(mongo, engine.path)
        await engine.reload()  # só retorna depois de drenar a consulta em voo
        assert engine._con is not old_con
        return await task

    _, rows, _ = asyncio.run(scenario())
    assert rows[0][0] > 0
    assert _rows(engine, "select count(*) from shop_orders_view") == [(3,)]


class FakeEngine:
    tables = {"orders"}

    def __init__(self):
        self.reloads = 0

    async def reload(self):
        self.reloads += 1


def test_concurrent_rebuild_single_flight():
    calls = []

    def build():
        calls.append(1)
        time.sleep(0.2)
        return True

    swapped = []
    service = SnapshotService(FakeEngine(), build, debounce_s=0, on_swap=swapped.append)

    async def run():
        return await asyncio.gather(*(service.refresh() for _ in range(5)))

    results = asyncio.run(run())
    assert len(calls) == 1 and service.engine.reloads == 1 and len(swapped) == 1
    assert results[0]["builds"] == 1 and results[0]["last_built_at"] is not None


def test_request_is_debounced_and_never_raises():
    calls = []

    def build():
        calls.append(1)
        raise RuntimeError("falha com ana@exemplo.com")

    service = SnapshotService(FakeEngine(), build, debounce_s=0.05)

    async def run():
        for _ in range(5):
            await service.request()
        await asyncio.sleep(0.4)

    asyncio.run(run())
    assert len(calls) == 1
    assert service.state.last_error == "RuntimeError" and not service.state.in_progress  # sem a mensagem (PII)


def test_guard_blocks_raw_collections_and_forbidden_join():
    for sql in (
        "select * from shop_customers",
        "select * from shop_addresses",
        "select * from users",
        "select * from shop_otp",
        "select * from shop_audit",
        "select * from shop_orders",
    ):
        with pytest.raises(UnsafeQueryError):
            validate_read_only_sql(sql, "duckdb", allowed_tables={"shop_customers", "shop_orders", "users"})
    with pytest.raises(UnsafeQueryError, match="reidentificação"):
        validate_read_only_sql(
            "select * from shop_orders_view o join customers c on c.customer_zip_code_prefix = o.destination_zip3",
            "duckdb",
        )
    with pytest.raises(UnsafeQueryError):
        validate_read_only_sql("select * from shop_customers_view, geolocation", "duckdb")
    ok = validate_read_only_sql("select count(*) from shop_orders_view", "duckdb", allowed_tables=set(SHOP_VIEW_TABLES))
    assert ok.tables == ["shop_orders_view"]


def test_catalog_known_tables_exclude_raw_and_accept_new_ones():
    service = CatalogService(None, None, known_tables={"orders", "shop_customers", "users", "shop_orders_view"})
    assert service.known_tables == {"orders", "shop_orders_view"}
    service.update_tables({"orders", "shop_payments", "shop_payments_view"})
    assert service.known_tables == {"orders", "shop_payments_view"}
    with pytest.raises(ValueError):
        asyncio.run(sample_table(None, "shop_customers"))  # Mongo bruto da loja nunca é amostrado


def _column(name: str) -> dict:
    return {"column_name": name, "data_type": "string", "description": "d", "semantic_role": "r", "confidence": "high"}


class RecordingLLM(FakeListChatModel):
    canned: dict = {}
    prompts: list = []

    def with_structured_output(self, schema, **kw):
        def respond(msgs):
            self.prompts.append(str(msgs))
            return schema.model_validate(self.canned[schema.__name__])

        return RunnableLambda(respond)


def test_catalog_prompt_has_no_customer_text(engine):
    llm = RecordingLLM(responses=["x"], canned={}, prompts=[])
    llm.canned["TableDescriptionOutput"] = {
        "table_name": "t",
        "description": "Pedidos",
        "business_domain": "vendas",
        "information_type": "transação",
        "granularity": "um por pedido",
        "analytical_use_cases": ["receita"],
    }
    service = CatalogService(None, llm, known_tables=engine.tables, engine=engine)

    async def run():
        for table, columns in VIEW_COLUMNS.items():
            llm.canned["ColumnMetadataOutput"] = {"table_name": table, "columns": [_column(c) for c in columns]}
            await service.get([table])

    asyncio.run(run())
    assert len(llm.prompts) == 2 * len(VIEW_COLUMNS)
    prompt = "\n".join(llm.prompts)
    assert "shop_orders_view" in prompt and "cama_mesa_banho" in prompt
    for text in PII_TEXT:
        assert text not in prompt
    assert "@" not in prompt.replace("Anita", "")


def test_pii_filter_masks_email_and_full_cep():
    assert (
        redact("meu email é ana@exemplo.com, cep 01310-100 e 01310100")
        == f"meu email é {REDACTED}, cep {REDACTED} e {REDACTED}"
    )
    assert redact("prefixo 013 e pedido de R$ 19820") == "prefixo 013 e pedido de R$ 19820"


def test_session_memory_keeps_no_raw_email_or_cep():
    memory = MemoryService(
        FakeListChatModel(responses=["x"]), max_turns=100, context_max_tokens=10_000, ttl_s=60, max_sessions=10
    )

    async def run():
        await memory.record_turn(
            "s", "pedidos de ana@exemplo.com no CEP 01310-100", "ok ana@exemplo.com", tool_note="01310100"
        )
        return await memory.render_context("s"), await memory.context_for_golden_record("s")

    for text in asyncio.run(run()):
        assert "ana@exemplo.com" not in text and "01310" not in text and REDACTED in text


def test_shop_golden_dataset_is_small_and_clean():
    assert len(SHOP_GOLDEN) == 5
    for row in SHOP_GOLDEN:
        assert set(row["tables"]) <= SHOP_VIEW_TABLES
        assert redact(row["question"] + row["answer"]) == row["question"] + row["answer"]
        assert row["is_approved"] is True


class FakeService:
    def __init__(self):
        self.refreshed = 0

    def status(self):
        return {
            "in_progress": False,
            "pending": False,
            "last_started_at": None,
            "last_built_at": None,
            "last_error": None,
            "builds": self.refreshed,
        }

    async def refresh(self):
        self.refreshed += 1
        return self.status()


def test_admin_snapshot_routes_require_admin(app, client, auth_db):
    admin, _ = auth_db.create_admin()
    legacy, _ = auth_db.create_non_admin()
    app.state.snapshot_service = fake = FakeService()
    try:
        for method, path in (("GET", "/api/v1/admin/snapshot"), ("POST", "/api/v1/admin/snapshot/refresh")):
            assert client.request(method, path).status_code == 401
            assert client.request(method, path, headers=legacy).status_code in (401, 403)
        assert client.get("/api/v1/admin/snapshot", headers=admin).json()["builds"] == 0
        res = client.post("/api/v1/admin/snapshot/refresh", headers=admin)
        assert res.status_code == 200 and res.json()["builds"] == 1 and fake.refreshed == 1
    finally:
        del app.state.snapshot_service
