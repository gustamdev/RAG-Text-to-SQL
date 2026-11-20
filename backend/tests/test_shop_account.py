"""E6: exportar, corrigir e excluir conta (LGPD), termos públicos e backoffice com PII mascarada."""

import pytest
from shop_helpers import V1, shop  # noqa: F401

from app.api.deps import get_app_db
from app.api.shop_deps import SnapshotRefresher, get_snapshot_refresher
from app.auth.security import hash_password
from app.core.timeutil import now

A = f"{V1}/shop/account"
PW = "senha-bem-longa-1"
ADDR = {"recipient": "Ana Souza", "zip": "01310100", "street": "Av. Paulista", "number": "1000",
        "complement": None, "district": "Bela Vista", "city": "São Paulo", "state": "SP"}  # fmt: skip


class Spy(SnapshotRefresher):
    calls = 0

    async def request(self) -> None:
        Spy.calls += 1


def seed(sh, cid, email):
    t = now()
    sh.run(sh.db["shop_customers"].insert_one({
        "_id": cid, "email": email, "nickname": "Ana Souza", "phone": "11987654321",
        "password_hash": hash_password(PW), "email_verified": True, "token_version": 0,
        "terms_version": "1", "created_at": t, "last_login_at": None, "deleted_at": None,
    }))  # fmt: skip
    sh.run(sh.db["shop_addresses"].insert_one({"_id": f"ad-{cid}", "customer_id": cid, "label": "Casa", **ADDR}))
    sh.run(sh.db["shop_orders"].insert_one({
        "order_id": f"o-{cid}", "customer_id": cid, "state": "paid", "items": [], "total_cents": 1500,
        "address": dict(ADDR), "timeline": [{"state": "paid", "at": t}], "created_at": t,
        "payment": {"status": "approved", "brand": "visa", "last4": "0001"},
    }))  # fmt: skip
    sh.run(sh.db["shop_payments"].insert_one({
        "order_id": f"o-{cid}", "customer_id": cid, "status": "approved", "brand": "visa", "last4": "0001",
        "amount_cents": 1500,
    }))  # fmt: skip
    sh.run(sh.db["shop_carts"].insert_one({"customer_id": cid, "items": [{"product_id": "p", "qty": 1}]}))


@pytest.fixture
def s(shop):  # noqa: F811
    Spy.calls = 0
    shop.client.app.dependency_overrides[get_snapshot_refresher] = Spy
    seed(shop, "cust-a", "ana@exemplo.com")
    seed(shop, "cust-b", "beto@exemplo.com")
    shop.login("cust-a")
    return shop


def delete(s, password=PW, confirm="EXCLUIR"):
    return s.client.request("DELETE", A, json={"password": password, "confirm": confirm})


def test_export_contains_own_data_only(s):
    res = s.client.get(f"{A}/export")
    body = res.json()

    assert res.status_code == 200
    assert body["customer"]["email"] == "ana@exemplo.com" and body["customer"]["phone"] == "11987654321"
    assert [o["order_id"] for o in body["orders"]] == ["o-cust-a"]
    assert len(body["addresses"]) == 1 and body["payments"][0]["last4"] == "0001"
    assert "password_hash" not in res.text and "beto" not in res.text and "cust-b" not in res.text


def test_patch_profile_and_validation(s):
    ok = s.client.patch(A, json={"nickname": " Aninha ", "phone": "(11) 98765-0000"})
    assert ok.status_code == 200 and ok.json()["nickname"] == "Aninha" and ok.json()["phone"] == "11987650000"
    assert s.client.patch(A, json={}).status_code == 422
    assert s.client.patch(A, json={"phone": "123"}).status_code == 422
    assert s.client.patch(A, json={"email": "x@y.com"}).status_code == 422  # extra=forbid
    assert s.client.patch(A, json={"phone": None}).json()["phone"] is None


def test_delete_requires_password_and_confirmation(s):
    assert delete(s, password="errada-errada-1").status_code == 401
    assert delete(s, confirm="sim").status_code == 422
    cust = s.run(s.db["shop_customers"].find_one({"_id": "cust-a"}))
    assert cust["deleted_at"] is None and Spy.calls == 0


def test_delete_account_anonymizes_orders(s):
    # pedido sem pagamento (payment=None) não pode derrubar a anonimização dos demais
    s.run(s.db["shop_orders"].insert_one({
        "order_id": "o-nopay", "customer_id": "cust-a", "state": "canceled", "items": [], "total_cents": 1,
        "address": dict(ADDR), "payment": None, "timeline": [], "created_at": now(),
    }))  # fmt: skip
    assert delete(s).status_code == 204

    cust = s.run(s.db["shop_customers"].find_one({"_id": "cust-a"}))
    assert cust["deleted_at"] and cust["email"] == "deleted-cust-a@anon.invalid"
    assert cust["nickname"] is None and cust["phone"] is None and cust["password_hash"] is None
    assert cust["token_version"] == 1  # revoga tokens emitidos antes
    order = s.run(s.db["shop_orders"].find_one({"order_id": "o-cust-a"}))
    assert order["total_cents"] == 1500 and order["address"]["recipient"] is None and order["address"]["zip"] is None
    assert order["payment"]["brand"] is None and order["payment"]["last4"] is None
    pay = s.run(s.db["shop_payments"].find_one({"order_id": "o-cust-a"}))
    assert pay["last4"] is None and pay["brand"] is None
    assert s.run(s.db["shop_addresses"].count_documents({"customer_id": "cust-a"})) == 0
    assert s.run(s.db["shop_carts"].count_documents({"customer_id": "cust-a"})) == 0
    assert Spy.calls == 1
    # dados de outro cliente intactos
    assert s.run(s.db["shop_orders"].find_one({"order_id": "o-cust-b"}))["address"]["zip"] == "01310100"
    assert s.run(s.db["shop_customers"].find_one({"_id": "cust-b"}))["email"] == "beto@exemplo.com"


def test_legal_is_public(client):
    res = client.get(f"{V1}/shop/legal")
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == "2" and "LGPD" in body["privacy"] and body["terms"]


def test_admin_lists_are_masked(s, auth_db):
    auth_db.db = s.db  # admin e loja no mesmo banco
    s.client.app.dependency_overrides[get_app_db] = lambda: s.db
    headers, _ = auth_db.create_admin()
    cust = s.client.get(f"{V1}/admin/shop/customers", headers=headers)
    orders = s.client.get(f"{V1}/admin/shop/orders", headers=headers)

    assert cust.status_code == orders.status_code == 200
    text = cust.text + orders.text
    for raw in ("ana@exemplo.com", "beto@exemplo.com", "11987654321", "01310100", "Ana Souza", "Paulista"):
        assert raw not in text
    row = next(r for r in cust.json()["items"] if r["id"] == "cust-a")
    assert row["email"] == "a***@exemplo.com" and row["phone"] == "*********21" and row["nickname"] == "A*** S***"
    assert orders.json()["items"][0]["zip"] == "013*****"
    events = [d["event"] for d in s.run(s.db["shop_audit"].find({}).to_list(None))]
    assert "admin_view_customers" in events and "admin_view_orders" in events


def test_admin_shop_requires_admin(s):
    s.client.app.dependency_overrides.pop(get_snapshot_refresher, None)
    assert s.client.get(f"{V1}/admin/shop/customers").status_code == 401


def test_delete_wrong_password_is_rate_limited_and_audited(s):
    codes = [delete(s, password="errada-errada-1").status_code for _ in range(6)]
    assert codes == [401] * 5 + [429]
    assert delete(s).status_code == 429  # senha certa também bloqueada na janela
    assert s.run(s.db["shop_audit"].count_documents({"event": "delete_fail"})) == 7
    assert s.run(s.db["shop_customers"].find_one({"_id": "cust-a"}))["deleted_at"] is None


def test_delete_purges_otp_and_retry_cleanup(s):
    s.run(s.db["shop_otp"].insert_one({"_id": "x", "email": "ana@exemplo.com", "purpose": "login"}))
    s.run(s.db["shop_otp"].insert_one({"_id": "y", "email": "beto@exemplo.com", "purpose": "login"}))
    assert delete(s).status_code == 204
    assert s.run(s.db["shop_otp"].count_documents({"email": "ana@exemplo.com"})) == 0
    assert s.run(s.db["shop_otp"].count_documents({"email": "beto@exemplo.com"})) == 1

    # limpeza parcial: conta já anonimizada, sobrou endereço -> o service repete sem senha
    from app.schemas.shop_account import DeleteAccountIn
    from app.services.shop_account import ShopAccount

    s.run(s.db["shop_addresses"].insert_one({"_id": "left", "customer_id": "cust-a"}))
    s.run(ShopAccount(s.db, Spy()).delete("cust-a", DeleteAccountIn(password="x" * 12, confirm="EXCLUIR")))
    assert s.run(s.db["shop_addresses"].count_documents({"customer_id": "cust-a"})) == 0


def test_export_headers_and_allowlist(s):
    s.run(
        s.db["shop_orders"].update_one({"order_id": "o-cust-a"}, {"$set": {"payment_id": "pay-1", "idempotency": "k"}})
    )
    s.run(s.db["shop_payments"].update_one({"order_id": "o-cust-a"}, {"$set": {"payment_id": "pay-1"}}))
    res = s.client.get(f"{A}/export")
    assert res.headers["cache-control"] == "no-store" and "attachment" in res.headers["content-disposition"]
    body = res.json()
    assert "timeline" not in body["orders"][0] and "payment_id" not in res.text and "idempotency" not in res.text


def test_me_returns_phone(s):
    from app.services.shop_auth_service import customer_out

    doc = s.run(s.db["shop_customers"].find_one({"_id": "cust-a"}))
    assert customer_out(doc).phone == "11987654321"


def test_admin_audit_has_ip_hmac_long_ttl_and_rate_limit(s, auth_db):
    from app.config import settings

    auth_db.db = s.db
    s.client.app.dependency_overrides[get_app_db] = lambda: s.db
    headers, _ = auth_db.create_admin()
    assert s.client.get(f"{V1}/admin/shop/customers", headers=headers).status_code == 200
    doc = s.run(s.db["shop_audit"].find_one({"event": "admin_view_customers"}))
    assert doc["ip_hmac"] and (doc["expires_at"] - doc["created_at"]).days >= 364
    for _ in range(settings.ADMIN_SHOP_RATE_LIMIT):
        res = s.client.get(f"{V1}/admin/shop/orders", headers=headers)
    assert res.status_code == 429
