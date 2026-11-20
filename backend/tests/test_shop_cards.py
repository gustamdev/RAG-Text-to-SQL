"""Cartões salvos (pagamento simulado): cadastro, limite, duplicata, isolamento, pagar com salvo, LGPD."""
# ruff: noqa: F811  (fixtures importadas de test_shop_checkout)

import asyncio
import logging

import pytest
from shop_helpers import V1, shop  # noqa: F401
from test_shop_account import PW, seed
from test_shop_checkout import CVV, OK, REFUSED, TIMEOUT, _addr, key, new_order, order_doc, s  # noqa: F401

from app.api.shop_deps import SnapshotRefresher, get_snapshot_refresher
from app.schemas.shop_orders import PayIn
from app.services import payment_gateway

C = f"{V1}/shop/account/cards"
LUHN_OK_UNKNOWN = "4111111111111111"  # Luhn válido, fora da lista de teste: salva com resultado "refused"
MASTER = "5555555555554444"
AMEX = "378282246310005"


def card(pan=OK, **over):
    body = {"card_number": pan, "holder": "ANA SOUZA", "exp_month": 12, "exp_year": 2099, "cvv": CVV}
    return {**body, **over}


def save(s, pan=OK, **over):
    return s.client.post(C, json=card(pan, **over))


def pay_saved(s, order_id, card_id, idem=None, cvv=CVV, **extra):
    body = {"saved_card_id": card_id, "cvv": cvv, **extra}
    return s.client.post(f"{V1}/shop/checkout/{order_id}/pay", json=body, headers={"Idempotency-Key": idem or key()})


def pay_new(s, order_id, pan=OK, **extra):
    body = {**card(pan), **extra}
    return s.client.post(f"{V1}/shop/checkout/{order_id}/pay", json=body, headers={"Idempotency-Key": key()})


def n_cards(s, cid="cust-a"):
    return s.run(s.db["shop_cards"].count_documents({"customer_id": cid}))


def test_create_list_delete(s):
    r = save(s)
    assert r.status_code == 201
    assert set(r.json()) == {"id", "brand", "last4", "exp_month", "exp_year"}
    assert r.json()["brand"] == "visa" and r.json()["last4"] == "0001" and r.json()["exp_year"] == 2099
    assert save(s, MASTER).json()["brand"] == "mastercard"
    assert [c["last4"] for c in s.client.get(C).json()] == ["0001", "4444"]
    assert s.client.delete(f"{C}/{r.json()['id']}").status_code == 204
    assert [c["last4"] for c in s.client.get(C).json()] == ["4444"]
    assert s.client.delete(f"{C}/{r.json()['id']}").status_code == 404


def test_stored_doc_has_no_pan_cvv_or_holder(s, caplog):
    caplog.set_level(logging.DEBUG)
    save(s, LUHN_OK_UNKNOWN, holder="FULANO DE TAL", cvv="7654")
    doc = s.run(s.db["shop_cards"].find_one({"customer_id": "cust-a"}))
    assert set(doc) == {"_id", "customer_id", "brand", "last4", "exp_month", "exp_year", "fingerprint", "outcome",
                        "created_at"}  # fmt: skip
    assert doc["outcome"] == "refused" and doc["last4"] == "1111"
    blob = " ".join(str(d) for col in ("shop_cards", "shop_audit") for d in s.run(s.db[col].find({}).to_list(100)))
    for secret in (LUHN_OK_UNKNOWN, "FULANO", "7654"):
        assert secret not in blob and secret not in caplog.text
    audit = s.run(s.db["shop_audit"].find_one({"event": "card_added"}))
    assert audit["meta"] == {"card_id": doc["_id"]}
    s.client.delete(f"{C}/{doc['_id']}")
    assert s.run(s.db["shop_audit"].find_one({"event": "card_removed"}))["meta"] == {"card_id": doc["_id"]}


def test_validation_costs_nothing(s):
    assert save(s, "4111111111111112").status_code == 422  # Luhn
    assert save(s, "12ab").status_code == 422
    assert save(s, exp_year=2020).status_code == 422  # vencido
    assert save(s, cvv="12").status_code == 422
    assert s.client.post(C, json=card(extra="x")).status_code == 422
    assert n_cards(s) == 0


def test_duplicate_returns_existing_with_new_expiry(s):
    first = save(s, "4242 4242-4242 0001")
    assert first.status_code == 201
    again = save(s, OK, exp_month=3, exp_year=2098)
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"] and n_cards(s) == 1
    assert (again.json()["exp_month"], again.json()["exp_year"]) == (3, 2098)
    assert s.client.get(C).json()[0]["exp_year"] == 2098  # persistiu
    assert save(s, OK, exp_month=3, exp_year=2098).status_code == 200  # mesma validade: nada muda
    assert save(s, OK, exp_year=2020).status_code == 422 and s.client.get(C).json()[0]["exp_year"] == 2098


def test_fingerprint_is_scoped_by_customer(s):
    save(s)
    s.login("cust-b")
    save(s)
    fps = {d["customer_id"]: d["fingerprint"] for d in s.run(s.db["shop_cards"].find({}).to_list(10))}
    assert len(fps) == 2 and fps["cust-a"] != fps["cust-b"]


def test_limit_of_three_is_atomic_and_duplicate_still_ok(s):
    for pan in (OK, REFUSED, MASTER):
        assert save(s, pan).status_code == 201
    r = save(s, LUHN_OK_UNKNOWN)
    assert r.status_code == 409 and r.json()["detail"] == "Limite de 3 cartões atingido."
    assert save(s, OK).status_code == 200 and n_cards(s) == 3  # mesmo cartão no limite: devolve o existente
    # corrida: duas inserções passam na contagem; a recontagem desfaz o excedente
    s.run(s.db["shop_cards"].delete_one({"last4": "4444"}))
    results = s.run(_gather_adds(s))
    assert n_cards(s) == 3 and sum(isinstance(r, Exception) for r in results) >= 1


async def _gather_adds(s):
    from app.schemas.shop_cards import CardIn
    from app.services.shop_cards import ShopCards

    svc = ShopCards(s.db)
    bodies = [CardIn(**card(p)) for p in (MASTER, LUHN_OK_UNKNOWN, AMEX)]
    return await asyncio.gather(*(svc.add("cust-a", b) for b in bodies), return_exceptions=True)


def test_isolation_between_customers(s):
    mine = save(s).json()["id"]
    s.login("cust-b")
    assert s.client.get(C).json() == []
    assert s.client.delete(f"{C}/{mine}").status_code == 404
    assert save(s).status_code == 201  # mesmo PAN em outro cliente não é duplicata
    s.login("cust-a")
    assert n_cards(s) == 1 and s.client.get(C).json()[0]["id"] == mine


def test_pay_with_saved_card_approved_and_replay(s):
    saved = save(s).json()
    order = new_order(s, qty=1)
    k = key()
    r = pay_saved(s, order["order_id"], saved["id"], idem=k)
    assert r.status_code == 200 and r.json()["order"]["state"] == "paid"
    assert r.json()["payment"] == {"status": "approved", "brand": "visa", "last4": "0001"}
    assert pay_saved(s, order["order_id"], saved["id"], idem=k).json() == r.json()  # idempotência
    assert s.run(s.db["shop_payments"].find_one({"order_id": order["order_id"]}))["attempts"] == 1
    assert n_cards(s) == 1  # pagar com salvo não duplica


def test_pay_with_saved_refused_and_unknown_pan_and_timeout(s):
    refused, unknown, timeout = (save(s, p).json()["id"] for p in (REFUSED, LUHN_OK_UNKNOWN, TIMEOUT))
    order = new_order(s, qty=1)
    for cid in (refused, unknown):
        r = pay_saved(s, order["order_id"], cid)
        assert r.status_code == 200 and r.json()["payment"]["status"] == "refused"
    assert pay_saved(s, order["order_id"], timeout).status_code == 504
    assert order_doc(s, order["order_id"])["state"] == "refused"


def test_saved_card_of_another_customer_is_404_and_spends_nothing(s):
    s.login("cust-b")
    theirs = save(s).json()["id"]
    s.login("cust-a")
    order = new_order(s, qty=1)
    r = pay_saved(s, order["order_id"], theirs)
    assert r.status_code == 404 and pay_saved(s, order["order_id"], "nao-existe").status_code == 404
    assert s.run(s.db["shop_payments"].find_one({"order_id": order["order_id"]})) is None
    assert order_doc(s, order["order_id"])["state"] == "created"


def test_saved_card_expired_is_refused(s):
    s.run(s.db["shop_cards"].insert_one({
        "_id": "old", "customer_id": "cust-a", "brand": "visa", "last4": "0001", "exp_month": 1, "exp_year": 2020,
        "fingerprint": "f", "outcome": "approved",
    }))  # fmt: skip
    order = new_order(s, qty=1)
    assert pay_saved(s, order["order_id"], "old").json()["payment"]["status"] == "refused"


def test_pay_body_forms_are_validated(s):
    saved = save(s).json()["id"]
    order = new_order(s, qty=1)
    oid = order["order_id"]
    assert pay_saved(s, oid, saved, cvv="abc").status_code == 422
    assert pay_saved(s, oid, saved, card_number=OK).status_code == 422  # as duas formas juntas
    assert pay_saved(s, oid, saved, save_card=False).status_code == 200  # save_card é ignorado com salvo
    bad = s.client.post(f"{V1}/shop/checkout/{oid}/pay", json={"cvv": CVV}, headers={"Idempotency-Key": key()})
    assert bad.status_code == 422
    assert s.run(s.db["shop_payments"].find_one({"order_id": oid}))["attempts"] == 1


def test_pay_does_not_save_card_by_default(s):
    assert PayIn.model_fields["save_card"].default is False
    order = new_order(s, qty=1)
    assert pay_new(s, order["order_id"]).json()["order"]["state"] == "paid"
    assert n_cards(s) == 0 and s.run(s.db["shop_audit"].count_documents({"event": "card_added"})) == 0


def test_checkout_saves_approved_card_with_opt_in(s):
    order = new_order(s, qty=1)
    assert pay_new(s, order["order_id"], save_card=True).status_code == 200
    cards = s.client.get(C).json()
    assert len(cards) == 1 and cards[0]["last4"] == "0001"
    assert s.run(s.db["shop_audit"].count_documents({"event": "card_added"})) == 1


def test_checkout_save_card_false_or_refused_does_not_save(s):
    order = new_order(s, qty=1)
    assert pay_new(s, order["order_id"], save_card=False).json()["order"]["state"] == "paid"
    assert n_cards(s) == 0
    order = new_order(s, qty=1)
    assert pay_new(s, order["order_id"], pan=REFUSED, save_card=True).json()["payment"]["status"] == "refused"
    assert n_cards(s) == 0


def test_checkout_without_room_pays_but_does_not_save(s):
    for pan in (REFUSED, MASTER, AMEX):
        save(s, pan)
    order = new_order(s, qty=1)
    r = pay_new(s, order["order_id"], save_card=True)
    assert r.status_code == 200 and r.json()["order"]["state"] == "paid"
    assert n_cards(s) == 3 and s.run(s.db["shop_cards"].find_one({"last4": "0001"})) is None


def test_checkout_save_does_not_duplicate_existing(s):
    save(s)
    order = new_order(s, qty=1)
    assert pay_new(s, order["order_id"], save_card=True).status_code == 200 and n_cards(s) == 1


def test_no_sensitive_data_anywhere_after_pay_and_save(s, caplog):
    caplog.set_level(logging.DEBUG)
    order = new_order(s, qty=1)
    pay_new(s, order["order_id"], pan=LUHN_OK_UNKNOWN, cvv="9876", save_card=True)
    order = new_order(s, qty=1)
    pay_new(s, order["order_id"], pan=OK, cvv="9876", save_card=True)
    blob = " ".join(
        str(d)
        for col in ("shop_cards", "shop_payments", "shop_audit", "shop_orders", "shop_idempotency")
        for d in s.run(s.db[col].find({}).to_list(100))
    )
    for secret in (LUHN_OK_UNKNOWN, OK, "9876", "ANA SOUZA"):
        assert secret not in blob.replace("Ana Souza", "") and secret not in caplog.text


def test_write_rate_limit_applies(s):
    codes = [s.client.delete(f"{C}/x{i}").status_code for i in range(22)]
    assert codes[0] == 404 and codes[-1] == 429


def test_pay_idempotency_digest_is_scoped_by_customer(s):
    order = new_order(s, qty=1)
    pay_new(s, order["order_id"], pan=LUHN_OK_UNKNOWN)
    mine = s.run(s.db["shop_idempotency"].find_one({"customer_id": "cust-a", "scope": "pay"}))["body_hash"]
    s.login("cust-b")
    s.addr_a = s.run(_addr(s, "cust-b"))  # checkout usa s.addr_a
    order = new_order(s, qty=1)
    pay_new(s, order["order_id"], pan=LUHN_OK_UNKNOWN)
    theirs = s.run(s.db["shop_idempotency"].find_one({"customer_id": "cust-b", "scope": "pay"}))["body_hash"]
    assert mine != theirs


def test_gateway_charge_saved_respects_outcome_and_expiry():
    run = asyncio.run
    assert run(payment_gateway.charge_saved("approved", "visa", "0001", 12, 2099)).status == "approved"
    assert run(payment_gateway.charge_saved("refused", "visa", "0002", 12, 2099)).status == "refused"
    assert run(payment_gateway.charge_saved("timeout", "visa", "0003", 12, 2099)).status == "timeout"
    assert run(payment_gateway.charge_saved("approved", "visa", "0001", 1, 2020)).status == "refused"


# --- LGPD --------------------------------------------------------------------------------------


class _Refresher(SnapshotRefresher):
    async def request(self) -> None:
        return None


@pytest.fixture
def acct(shop):  # noqa: F811
    shop.client.app.state.shop_write_limiter = None
    shop.client.app.dependency_overrides[get_snapshot_refresher] = _Refresher
    seed(shop, "cust-a", "ana@exemplo.com")
    seed(shop, "cust-b", "beto@exemplo.com")
    shop.login("cust-a")
    return shop


def test_export_includes_cards_without_internals(acct):
    save(acct, MASTER)
    acct.login("cust-b")
    save(acct, AMEX)
    acct.login("cust-a")
    res = acct.client.get(f"{V1}/shop/account/export")
    (exported,) = res.json()["cards"]
    assert set(exported) == {"id", "brand", "last4", "exp_month", "exp_year", "created_at"}
    assert exported["id"] == acct.client.get(C).json()[0]["id"] and exported["created_at"]
    assert (exported["brand"], exported["last4"]) == ("mastercard", "4444")
    for hidden in ("fingerprint", "outcome", "cust-b", "5555", "0005"):
        assert hidden not in res.text


def test_delete_account_removes_cards(acct):
    save(acct, MASTER)
    acct.login("cust-b")
    save(acct, AMEX)
    acct.login("cust-a")
    r = acct.client.request("DELETE", f"{V1}/shop/account", json={"password": PW, "confirm": "EXCLUIR"})
    assert r.status_code == 204
    assert n_cards(acct, "cust-a") == 0 and n_cards(acct, "cust-b") == 1
