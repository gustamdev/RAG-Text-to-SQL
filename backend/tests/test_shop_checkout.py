"""E5: checkout, pagamento simulado, idempotência, estoque concorrente, IDOR e vazamento de PAN/CVV."""

import asyncio
import logging
import uuid
from datetime import timedelta

import pytest
from shop_helpers import V1, shop  # noqa: F401

from app.api.shop_deps import SnapshotRefresher, get_snapshot_refresher
from app.core.timeutil import now
from app.database.repos.shop_stock import ShopStockRepo
from app.schemas.shop_orders import CheckoutIn
from app.services.shop_checkout import ShopCheckout

OK, REFUSED, TIMEOUT = "4242424242420001", "4242424242420002", "4242424242420003"
REAL_PAN, CVV = "4111111111111111", "987"
ADDR = {
    "recipient": "Ana Souza", "zip": "01310100", "street": "Av. Paulista", "number": "1000",
    "complement": None, "district": "Bela Vista", "city": "São Paulo", "state": "SP",
}  # fmt: skip


class Spy(SnapshotRefresher):
    calls = 0

    async def request(self) -> None:
        Spy.calls += 1


@pytest.fixture
def s(shop):  # noqa: F811
    Spy.calls = 0
    shop.client.app.state.shop_write_limiter = None
    shop.client.app.dependency_overrides[get_snapshot_refresher] = Spy
    shop.run(shop.db["shop_idempotency"].create_index([("customer_id", 1), ("scope", 1), ("key", 1)], unique=True))
    shop.product("p-a", price_cents=1000, stock=5, title="Item A")
    shop.product("p-b", price_cents=250, stock=5, title="Item B")
    shop.login("cust-a")
    shop.addr_a = shop.run(_addr(shop, "cust-a"))
    return shop


async def _addr(shop, customer_id):  # noqa: F811
    doc = {"_id": uuid.uuid4().hex, "customer_id": customer_id, "label": "Casa", "is_default": True, **ADDR}
    await shop.db["shop_addresses"].insert_one(doc)
    return doc["_id"]


def key():
    return uuid.uuid4().hex


def add(s, pid, qty=1):
    assert s.client.post(f"{V1}/shop/cart/items", json={"product_id": pid, "qty": qty}).status_code == 200


def checkout(s, idem=None, address_id=None, **extra):
    body = {"address_id": address_id or s.addr_a, "shipping_option": "standard", **extra}
    return s.client.post(f"{V1}/shop/checkout", json=body, headers={"Idempotency-Key": idem or key()})


def pay(s, order_id, pan=OK, idem=None, cvv=CVV):
    body = {"card_number": pan, "holder": "ANA SOUZA", "exp_month": 12, "exp_year": 2099, "cvv": cvv}
    return s.client.post(f"{V1}/shop/checkout/{order_id}/pay", json=body, headers={"Idempotency-Key": idem or key()})


def stock(s, pid="p-a"):
    return s.run(s.db["shop_products"].find_one({"product_id": pid}))["stock"]


def order_doc(s, order_id):
    return s.run(s.db["shop_orders"].find_one({"order_id": order_id}))


def new_order(s, pid="p-a", qty=2):
    s.client.delete(f"{V1}/shop/cart")  # o carrinho só esvazia no pagamento aprovado
    add(s, pid, qty)
    r = checkout(s)
    assert r.status_code == 201, r.text
    return r.json()


def test_total_ignores_client_price_and_state(s):
    add(s, "p-a", 2)
    # campos do cliente (preço, total, estado, frete) são rejeitados: extra=forbid
    r = checkout(s, total_cents=1, state="paid", freight_cents=0)
    assert r.status_code == 422
    r = checkout(s)
    order = r.json()
    assert r.status_code == 201 and order["state"] == "created" and order["payment"] is None
    assert order["subtotal_cents"] == 2000 and order["freight_cents"] > 0
    assert order["total_cents"] == 2000 + order["freight_cents"] and order["discount_cents"] == 0
    assert order["items"][0]["title"] == "Item A" and order["address"]["zip"] == "01310100"
    assert stock(s) == 3  # reservado


def test_requires_idempotency_key_and_cart(s):
    body = {"address_id": s.addr_a, "shipping_option": "standard"}
    assert s.client.post(f"{V1}/shop/checkout", json=body).status_code == 422
    assert checkout(s).status_code == 409  # carrinho vazio


def test_blocked_cart_cannot_checkout(s):
    add(s, "p-a", 2)
    s.set_product("p-a", price_cents=1500)  # price_changed sem ack
    assert checkout(s).status_code == 409
    assert stock(s) == 5


def test_other_customers_address_is_404(s):
    other = s.run(_addr(s, "cust-b"))
    add(s, "p-a")
    assert checkout(s, address_id=other).status_code == 404
    assert checkout(s, address_id="nope").status_code == 404


def test_replay_same_key_same_order_one_decrement(s):
    add(s, "p-a", 2)
    k = key()
    first, second = checkout(s, k), checkout(s, k)
    assert first.status_code == second.status_code == 201 and first.json() == second.json()
    assert s.run(s.db["shop_orders"].count_documents({})) == 1 and stock(s) == 3


def test_same_key_different_body_422(s):
    add(s, "p-a")
    k = key()
    assert checkout(s, k).status_code == 201
    other = s.client.post(
        f"{V1}/shop/checkout",
        json={"address_id": s.addr_a, "shipping_option": "economy"},
        headers={"Idempotency-Key": k},
    )
    assert other.status_code == 422


def test_pay_approved_flow(s):
    order = new_order(s)
    r = pay(s, order["order_id"])
    body = r.json()
    assert r.status_code == 200 and body["payment"] == {"status": "approved", "brand": "visa", "last4": "0001"}
    assert body["order"]["state"] == "paid" and body["order"]["reservation_expires_at"] is None
    assert [t["state"] for t in body["order"]["timeline"]] == ["created", "paid"]
    assert stock(s) == 3  # baixa definitiva (uma só)
    assert s.client.get(f"{V1}/shop/cart").json()["items"] == []
    assert Spy.calls == 1
    audit = s.run(s.db["shop_audit"].find({"event": "order_paid"}).to_list(10))
    assert len(audit) == 1 and "cust-a" not in str(audit)


def test_pay_replay_one_charge(s):
    order = new_order(s)
    k = key()
    a, b = pay(s, order["order_id"], idem=k), pay(s, order["order_id"], idem=k)
    assert a.json() == b.json() and Spy.calls == 1
    assert s.run(s.db["shop_payments"].count_documents({})) == 1
    assert s.run(s.db["shop_payments"].find_one({}))["attempts"] == 1


def test_pay_twice_different_keys_approves_once(s):
    order = new_order(s)
    assert pay(s, order["order_id"]).status_code == 200
    assert pay(s, order["order_id"]).status_code == 409
    assert Spy.calls == 1 and stock(s) == 3


def test_refused_then_retry_and_refresher_only_on_approved(s):
    order = new_order(s)
    r = pay(s, order["order_id"], pan=REFUSED)
    assert r.status_code == 200 and r.json()["payment"]["status"] == "refused"
    assert r.json()["order"]["state"] == "refused" and Spy.calls == 0
    assert order_doc(s, order["order_id"])["reservation_expires_at"] is not None and stock(s) == 3
    assert pay(s, order["order_id"], pan=OK).json()["order"]["state"] == "paid" and Spy.calls == 1


def test_real_or_unknown_pan_refused_generic_without_leak(s):
    order = new_order(s)
    r = pay(s, order["order_id"], pan=REAL_PAN)
    assert r.status_code == 200 and r.json()["payment"]["status"] == "refused"
    assert REAL_PAN not in r.text and CVV not in r.text and Spy.calls == 0
    bad = pay(s, order["order_id"], pan="4111111111111112")  # Luhn inválido
    assert bad.status_code == 422
    assert pay(s, order["order_id"], pan="12ab").status_code == 422


def test_pan_cvv_never_stored_or_logged(s, caplog):
    caplog.set_level(logging.DEBUG)
    order = new_order(s)
    for pan in (REAL_PAN, OK):
        pay(s, order["order_id"], pan=pan)
    pay(s, order["order_id"], pan="4111111111111112")
    blob = " ".join(
        str(d)
        for col in ("shop_payments", "shop_audit", "shop_orders", "shop_idempotency")
        for d in s.run(s.db[col].find({}).to_list(100))
    )
    for secret in (REAL_PAN, OK, CVV, "ANA SOUZA"):
        assert secret not in blob.replace("Ana Souza", "") and secret not in caplog.text
    assert "1111" in blob  # só last4


def test_timeout_not_persisted_in_idempotency(s):
    order = new_order(s)
    k = key()
    r = pay(s, order["order_id"], pan=TIMEOUT, idem=k)
    assert r.status_code == 504 and r.json()["detail"] == "Não conseguimos confirmar. Tente novamente."
    assert order_doc(s, order["order_id"])["state"] == "created"
    assert s.run(s.db["shop_payments"].find_one({}))["status"] == "timeout"
    assert s.run(s.db["shop_idempotency"].count_documents({"scope": "pay"})) == 0
    assert Spy.calls == 0
    assert pay(s, order["order_id"], pan=TIMEOUT, idem=k).status_code == 504  # reexecuta
    assert s.run(s.db["shop_payments"].find_one({}))["attempts"] == 2


def test_pay_attempt_limit(s):
    order = new_order(s)
    for _ in range(5):
        assert pay(s, order["order_id"], pan=REFUSED).status_code == 200
    assert pay(s, order["order_id"], pan=OK).status_code == 409


def test_idor_order_is_404(s):
    order = new_order(s)
    s.login("cust-b")
    oid = order["order_id"]
    assert s.client.get(f"{V1}/shop/orders/{oid}").status_code == 404
    assert pay(s, oid).status_code == 404
    assert s.client.post(f"{V1}/shop/orders/{oid}/cancel").status_code == 404
    assert s.client.get(f"{V1}/shop/orders").json()["items"] == []
    s.login("cust-a")
    assert s.client.get(f"{V1}/shop/orders/{oid}").status_code == 200
    assert [o["order_id"] for o in s.client.get(f"{V1}/shop/orders").json()["items"]] == [oid]


def test_cancel_returns_stock_only_active(s):
    order = new_order(s)
    r = s.client.post(f"{V1}/shop/orders/{order['order_id']}/cancel")
    assert r.status_code == 200 and r.json()["state"] == "canceled" and stock(s) == 5
    assert s.client.post(f"{V1}/shop/orders/{order['order_id']}/cancel").status_code == 409
    assert stock(s) == 5  # não devolve duas vezes
    paid = new_order(s)
    pay(s, paid["order_id"])
    assert s.client.post(f"{V1}/shop/orders/{paid['order_id']}/cancel").status_code == 409


@pytest.fixture
def lose_p_b(monkeypatch):
    """Simula perder a corrida pelo item p-b: a reserva dele falha mesmo com o carrinho válido."""
    real = ShopStockRepo.reserve

    async def reserve(self, pid, qty):
        return False if pid == "p-b" else await real(self, pid, qty)

    monkeypatch.setattr(ShopStockRepo, "reserve", reserve)


def test_compensation_when_second_item_fails(s, lose_p_b):
    add(s, "p-a", 2)
    add(s, "p-b", 2)
    r = checkout(s)
    assert r.status_code == 409 and r.json()["detail"] == "Estoque insuficiente."
    assert r.json()["items"] == [{"product_id": "p-b", "available": 5}]
    assert stock(s, "p-a") == 5 and stock(s, "p-b") == 5  # p-a devolvido
    assert s.run(s.db["shop_orders"].count_documents({})) == 0
    assert s.run(s.db["shop_idempotency"].count_documents({})) == 0  # chave liberada


def test_50_concurrent_last_item_one_wins(s):
    s.set_product("p-a", stock=1)
    customers = [f"c{i}" for i in range(50)]
    addrs = {c: s.run(_addr(s, c)) for c in customers}
    for c in customers:
        s.run(s.db["shop_carts"].insert_one({
            "customer_id": c, "updated_at": now(),
            "items": [{"product_id": "p-a", "qty": 1, "added_at": now(), "seen_price_cents": 1000}],
        }))  # fmt: skip

    async def go(c):
        try:
            return await ShopCheckout(s.db).checkout(
                c, key(), CheckoutIn(address_id=addrs[c], shipping_option="standard")
            )
        except Exception as exc:  # noqa: BLE001
            return exc

    results = s.run(_gather(go, customers))
    wins = [r for r in results if isinstance(r, tuple) and r[0] == 201]
    assert len(wins) == 1 and stock(s) == 0
    assert s.run(s.db["shop_orders"].count_documents({})) == 1


async def _gather(fn, items):
    return await asyncio.gather(*(fn(i) for i in items))


def test_concurrent_same_key_creates_one_order(s):
    add(s, "p-a", 2)
    k = key()

    async def go(_):
        try:
            return await ShopCheckout(s.db).checkout(
                "cust-a", k, CheckoutIn(address_id=s.addr_a, shipping_option="standard")
            )
        except Exception as exc:  # noqa: BLE001
            return exc

    results = s.run(_gather(go, range(10)))
    assert sum(1 for r in results if isinstance(r, tuple)) >= 1
    assert s.run(s.db["shop_orders"].count_documents({})) == 1 and stock(s) == 3


def test_expire_reservations_returns_stock(s):
    expired = new_order(s, qty=2)
    live = new_order(s, "p-b", 1)
    paid = new_order(s, "p-a", 1)
    pay(s, paid["order_id"])
    past = now() - timedelta(minutes=1)
    s.run(s.db["shop_orders"].update_one({"order_id": expired["order_id"]}, {"$set": {"reservation_expires_at": past}}))
    s.run(s.db["shop_orders"].update_one({"order_id": paid["order_id"]}, {"$set": {"reservation_expires_at": past}}))
    assert stock(s) == 2  # 5 - 2 - 1
    assert s.run(ShopCheckout(s.db).expire_reservations(now())) == 1
    assert stock(s) == 4 and order_doc(s, expired["order_id"])["state"] == "canceled"
    assert order_doc(s, live["order_id"])["state"] == "created"
    assert order_doc(s, paid["order_id"])["state"] == "paid"
    assert s.run(ShopCheckout(s.db).expire_reservations(now())) == 0  # idempotente


def test_pay_after_expiry_409(s):
    order = new_order(s)
    past = now() - timedelta(minutes=1)
    s.run(s.db["shop_orders"].update_one({"order_id": order["order_id"]}, {"$set": {"reservation_expires_at": past}}))
    r = pay(s, order["order_id"])
    assert r.status_code == 409 and "expirada" in r.json()["detail"]


def test_write_rate_limit(s):
    codes = [checkout(s).status_code for _ in range(22)]
    assert codes[-1] == 429
