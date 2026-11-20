"""LGPD da loja: aviso, retenção, exclusão com pedidos abertos, snapshot pendente, export e auditoria admin."""

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from shop_helpers import V1, shop  # noqa: F401
from test_shop_account import A, Spy, seed

from app.api.deps import get_app_db
from app.api.shop_deps import SnapshotRefresher, get_snapshot_refresher
from app.core.timeutil import now
from app.services import shop_account as account_mod
from app.services.shop_account import SNAPSHOT_PENDING, ShopAccount
from app.services.shop_admin import ShopAdmin
from app.services.shop_legal import legal
from app.services.shop_retention import ShopRetention

BACKEND = Path(__file__).resolve().parents[1]


class Boom(SnapshotRefresher):
    async def request(self) -> None:
        raise RuntimeError("snapshot fora")


@pytest.fixture
def s(shop):  # noqa: F811
    Spy.calls = 0
    shop.client.app.dependency_overrides[get_snapshot_refresher] = Spy
    seed(shop, "cust-a", "ana@exemplo.com")
    shop.login("cust-a")
    return shop


def test_privacy_notice_is_complete_and_demo_is_clear():
    out = legal()
    p = out.privacy
    for needle in ("Controlador", "Encarregado", "ANPD", "OpenAI", "LangSmith", "SMTP", "art. 7º, V", "15 dias",
                   "Seus direitos (art. 18)", "não é consentimento", "dias"):  # fmt: skip
        assert needle in p, needle
    assert "loja simulada" in out.terms and "nenhum pagamento é cobrado" in out.terms
    assert "não compartilhamos" not in p.lower()


def test_langsmith_masks_io_by_default_when_tracing_on():
    code = "import os, app.config; print(os.environ['LANGSMITH_HIDE_INPUTS'], os.environ['LANGSMITH_HIDE_OUTPUTS'])"
    env = {**os.environ, "LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "k", "PYTHONPATH": str(BACKEND / "src")}
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=BACKEND, capture_output=True, text=True)
    assert out.stdout.split() == ["true", "true"], out.stderr


def test_delete_cancels_open_orders_and_returns_stock(s):
    s.product("p1", stock=3)
    s.run(s.db["shop_orders"].insert_one({
        "order_id": "open-1", "customer_id": "cust-a", "state": "created", "items": [{"product_id": "p1", "qty": 2}],
        "address": {}, "timeline": [], "created_at": now(), "reservation_expires_at": now() + timedelta(hours=1),
    }))  # fmt: skip
    body = {"password": "senha-bem-longa-1", "confirm": "EXCLUIR"}
    assert s.client.request("DELETE", A, json=body).status_code == 204
    assert s.run(s.db["shop_orders"].find_one({"order_id": "open-1"}))["state"] == "canceled"
    assert s.run(s.db["shop_products"].find_one({"product_id": "p1"}))["stock"] == 5
    assert s.run(s.db["shop_orders"].find_one({"order_id": "o-cust-a"}))["state"] == "paid"


def test_snapshot_failure_sets_flag_and_loop_retries(s):
    s.run(ShopAccount(s.db, Boom()).erase_inactive({"_id": "cust-a", "email": "ana@exemplo.com"}))
    retention = ShopRetention(s.db, Spy())
    assert s.run(s.db["shop_flags"].find_one({"_id": SNAPSHOT_PENDING})) is not None
    assert s.run(retention.retry_snapshot()) is True and Spy.calls == 1
    assert s.run(s.db["shop_flags"].find_one({"_id": SNAPSHOT_PENDING})) is None
    assert s.run(retention.retry_snapshot()) is False

    s.run(s.db["shop_flags"].insert_one({"_id": SNAPSHOT_PENDING}))
    with pytest.raises(RuntimeError):
        s.run(ShopRetention(s.db, Boom()).retry_snapshot())
    assert s.run(s.db["shop_flags"].find_one({"_id": SNAPSHOT_PENDING})) is not None  # segue pendente


def test_retention_job(s):
    old = now() - timedelta(days=3000)
    seed(s, "cust-old", "velho@exemplo.com")
    s.run(s.db["shop_customers"].update_one({"_id": "cust-old"}, {"$set": {"created_at": old, "last_login_at": old}}))
    s.run(s.db["shop_orders"].update_one({"order_id": "o-cust-old"}, {"$set": {"created_at": old}}))
    s.run(s.db["shop_customers"].insert_many([
        {"_id": "unv", "email": "u@x.com", "email_verified": False, "deleted_at": None, "created_at": old},
        {"_id": "unv-new", "email": "n@x.com", "email_verified": False, "deleted_at": None, "created_at": now()},
    ]))  # fmt: skip
    s.run(s.db["shop_orders"].insert_one({"order_id": "recent", "customer_id": "cust-a", "state": "paid",
                                          "created_at": now()}))  # fmt: skip

    counts = s.run(ShopRetention(s.db, Spy()).run())

    assert counts["unverified"] == 1 and counts["inactive"] == 1 and counts["orders"] == 1
    assert s.run(s.db["shop_customers"].find_one({"_id": "unv"})) is None
    assert s.run(s.db["shop_customers"].find_one({"_id": "unv-new"})) is not None
    assert s.run(s.db["shop_orders"].find_one({"order_id": "o-cust-old"})) is None
    assert s.run(s.db["shop_payments"].find_one({"order_id": "o-cust-old"})) is None
    assert s.run(s.db["shop_addresses"].count_documents({"customer_id": "cust-old"})) == 0
    assert s.run(s.db["shop_customers"].find_one({"_id": "cust-old"}))["deleted_at"]
    assert (
        s.run(s.db["shop_orders"].find_one({"order_id": "recent"}))
        and s.run(s.db["shop_customers"].find_one({"_id": "cust-a"}))["deleted_at"] is None
    )  # login None + created_at recente: fica
    assert Spy.calls == 2  # uma por conta anonimizada + uma pelos pedidos purgados


def test_retention_skips_account_that_logged_in_mid_pass(s):
    old = now() - timedelta(days=3000)
    seed(s, "cust-old", "velho@exemplo.com")
    s.run(s.db["shop_customers"].update_one({"_id": "cust-old"}, {"$set": {"created_at": old, "last_login_at": now()}}))
    stale = {"_id": "cust-old", "email": "velho@exemplo.com"}  # lote lido antes do login
    assert s.run(ShopAccount(s.db, Spy()).erase_inactive(stale, now() - timedelta(days=100))) is False
    assert s.run(s.db["shop_customers"].find_one({"_id": "cust-old"}))["deleted_at"] is None


def test_retention_batches_loop_past_batch_size(s, monkeypatch):
    import app.services.shop_retention as ret

    monkeypatch.setattr(ret, "BATCH", 2)
    old = now() - timedelta(days=3000)
    s.run(s.db["shop_customers"].insert_many(
        [{"_id": f"u{i}", "email": f"u{i}@x.com", "email_verified": False, "deleted_at": None, "created_at": old}
         for i in range(5)]
    ))  # fmt: skip
    assert s.run(ShopRetention(s.db, Spy()).run())["unverified"] == 5


def test_retry_snapshot_clears_before_request_and_recreates_on_failure(s):
    s.run(s.db["shop_flags"].insert_one({"_id": SNAPSHOT_PENDING}))
    seen = []

    class Probe:
        async def request(self):
            seen.append(await s.db["shop_flags"].find_one({"_id": SNAPSHOT_PENDING}))

    assert s.run(ShopRetention(s.db, Probe()).retry_snapshot()) is True and seen == [None]


def test_export_has_art19_and_warns_on_truncation(s, monkeypatch):
    body = s.client.get(f"{A}/export").json()
    assert body["truncated"] == {"orders": False, "payments": False} and "warning" not in body
    art = body["art19"]
    assert {t["name"].split()[0] for t in art["third_parties"]} >= {"OpenAI", "LangSmith"}
    assert art["origin"] and art["purposes"] and art["retention"]

    monkeypatch.setattr(account_mod, "EXPORT_LIMIT", 1)
    body = s.client.get(f"{A}/export").json()
    assert body["truncated"]["orders"] is True and "limitada" in body["warning"]


def test_admin_audit_records_purpose_and_precedes_read(s, auth_db):
    auth_db.db = s.db
    s.client.app.dependency_overrides[get_app_db] = lambda: s.db
    headers, _ = auth_db.create_admin()
    assert s.client.get(f"{V1}/admin/shop/orders?purpose=auditoria", headers=headers).status_code == 200
    assert s.client.get(f"{V1}/admin/shop/customers?purpose=x", headers=headers).status_code == 422
    doc = s.run(s.db["shop_audit"].find_one({"event": "admin_view_orders"}))
    assert doc["meta"] == {"page": 1, "purpose": "auditoria"}


def test_admin_read_blocked_when_audit_write_fails(s, monkeypatch):
    svc = ShopAdmin(s.db)
    read = []

    async def fail(*a, **k):
        raise RuntimeError("audit down")

    async def spy(*a, **k):
        read.append(1)
        return [], 0

    monkeypatch.setattr(svc.audit, "add", fail)
    monkeypatch.setattr(svc.customers, "page", spy)
    with pytest.raises(RuntimeError):
        s.run(svc.customer_page("admin-1", "1.2.3.4", 1, 20))
    assert read == []


def test_security_headers_present(client):
    res = client.get(f"{V1}/shop/legal")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["referrer-policy"] == "no-referrer" and res.headers["x-frame-options"] == "DENY"
