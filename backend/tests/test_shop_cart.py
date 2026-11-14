"""E3: carrinho no servidor (total, limites, estoque, avisos/ack, IDOR, merge)."""

import pytest
from shop_helpers import V1, shop  # noqa: F401

from app.api.shop_deps import get_current_customer
from app.config import settings

C = f"{V1}/shop/cart"


@pytest.fixture
def cart(shop):  # noqa: F811
    shop.product("p-a", price_cents=1000, stock=5, title="Item A")
    shop.product("p-b", price_cents=250, stock=20, title="Item B")
    shop.product("p-zero", price_cents=500, stock=0)
    shop.login("cust-a")
    return shop


def add(cart, pid, qty=1):
    return cart.client.post(f"{C}/items", json={"product_id": pid, "qty": qty})


def test_requires_customer(cart):
    cart.client.app.dependency_overrides.pop(get_current_customer)  # volta ao dependency real: sem token, 401
    assert cart.client.get(C).status_code == 401


def test_empty_cart(cart):
    assert cart.client.get(C).json() == {
        "items": [], "item_count": 0, "subtotal_cents": 0, "blocked": False, "updated_at": None,
    }  # fmt: skip


def test_cart_total_server_side(cart):
    add(cart, "p-a", 2)
    body = add(cart, "p-b", 3).json()
    assert body["subtotal_cents"] == 2 * 1000 + 3 * 250 and body["item_count"] == 5 and not body["blocked"]
    assert {i["product_id"]: i["line_total_cents"] for i in body["items"]} == {"p-a": 2000, "p-b": 750}
    # o servidor guarda só product_id/qty/preço visto: mudar o preço no catálogo muda o total, nunca o cliente
    cart.set_product("p-b", price_cents=300)
    assert cart.client.get(C).json()["subtotal_cents"] == 2000 + 900


@pytest.mark.parametrize("extra", [{"price_cents": 1}, {"unit_price_cents": 1}, {"customer_id": "x"}, {"total": 1}])
def test_client_cannot_send_price_or_owner(cart, extra):
    r = cart.client.post(f"{C}/items", json={"product_id": "p-a", "qty": 1, **extra})
    assert r.status_code == 422
    assert cart.client.get(C).json()["items"] == []


def test_qty_limits(cart):
    assert add(cart, "p-b", 11).status_code == 422
    assert add(cart, "p-b", 0).status_code == 422
    assert add(cart, "p-b", 6).status_code == 200
    body = add(cart, "p-b", 6).json()  # soma passa de 10: respeita o teto
    assert body["items"][0]["qty"] == settings.SHOP_CART_MAX_QTY == 10


def test_cart_item_limit(cart, monkeypatch):
    monkeypatch.setattr(settings, "SHOP_CART_MAX_ITEMS", 1)
    assert add(cart, "p-a").status_code == 200
    r = add(cart, "p-b")
    assert (r.status_code, r.json()) == (409, {"detail": "Limite de itens do carrinho atingido."})
    assert add(cart, "p-a").status_code == 200  # linha existente ainda aceita soma


def test_out_of_stock_and_unknown(cart):
    r = add(cart, "p-zero")
    assert (r.status_code, r.json()) == (409, {"detail": "Produto sem estoque suficiente."})
    assert add(cart, "p-a", 6).status_code == 409  # estoque 5
    assert add(cart, "nao-existe").status_code == 404
    assert cart.client.get(C).json()["items"] == []


def test_patch_qty_respects_stock_and_validation(cart):
    add(cart, "p-a")
    assert cart.client.patch(f"{C}/items/p-a", json={"qty": 4}).json()["item_count"] == 4
    assert cart.client.patch(f"{C}/items/p-a", json={"qty": 6}).status_code == 409
    assert cart.client.patch(f"{C}/items/p-a", json={}).status_code == 422
    assert cart.client.patch(f"{C}/items/p-a", json={"qty": 2, "price_cents": 1}).status_code == 422
    assert cart.client.patch(f"{C}/items/p-b", json={"qty": 1}).status_code == 404


def test_price_changed_blocks_until_ack(cart):
    add(cart, "p-a", 2)
    cart.set_product("p-a", price_cents=1200)
    body = cart.client.get(C).json()
    assert body["blocked"] and body["items"][0]["warning"] == "price_changed"
    assert body["items"][0]["unit_price_cents"] == 1200 and body["subtotal_cents"] == 2400  # preço atual, não o visto
    body = cart.client.patch(f"{C}/items/p-a", json={"ack": True}).json()
    assert not body["blocked"] and body["items"][0]["warning"] is None
    assert cart.client.get(C).json()["blocked"] is False  # persistido


def test_stock_reduced_adjusts_qty_and_ack_persists(cart):
    add(cart, "p-a", 4)
    cart.set_product("p-a", stock=2)
    line = cart.client.get(C).json()["items"][0]
    assert (line["warning"], line["qty"], line["line_total_cents"]) == ("stock_reduced", 2, 2000)
    body = cart.client.patch(f"{C}/items/p-a", json={"ack": True}).json()
    assert not body["blocked"] and body["items"][0]["qty"] == 2
    cart.set_product("p-a", stock=5)  # estoque volta: a qty confirmada não sobe sozinha
    assert cart.client.get(C).json()["items"][0]["qty"] == 2


def test_out_of_stock_cannot_be_acked_only_removed(cart):
    add(cart, "p-a", 2)
    add(cart, "p-b", 1)
    cart.set_product("p-a", stock=0)
    body = cart.client.get(C).json()
    line = next(i for i in body["items"] if i["product_id"] == "p-a")
    assert line["warning"] == "out_of_stock" and body["blocked"]
    assert body["subtotal_cents"] == 250 and body["item_count"] == 1  # indisponível não soma
    assert cart.client.patch(f"{C}/items/p-a", json={"ack": True}).status_code == 409
    assert cart.client.delete(f"{C}/items/p-a").json()["blocked"] is False


def test_delete_item_and_clear(cart):
    add(cart, "p-a")
    add(cart, "p-b")
    assert cart.client.delete(f"{C}/items/nada").status_code == 404
    assert [i["product_id"] for i in cart.client.delete(f"{C}/items/p-a").json()["items"]] == ["p-b"]
    assert cart.client.delete(C).json()["items"] == []


def test_idor_other_customer_cart_is_404(cart):
    add(cart, "p-a", 2)
    cart.login("cust-b")
    assert cart.client.get(C).json()["items"] == []  # nunca vê o carrinho de A
    assert cart.client.patch(f"{C}/items/p-a", json={"qty": 1}).status_code == 404
    assert cart.client.patch(f"{C}/items/p-a", json={"ack": True}).status_code == 404
    assert cart.client.delete(f"{C}/items/p-a").status_code == 404
    cart.client.delete(C)  # esvaziar o "meu" carrinho não toca o de A
    cart.login("cust-a")
    assert cart.client.get(C).json()["item_count"] == 2


def test_merge_ignores_invalid_and_sums(cart):
    add(cart, "p-a", 1)
    r = cart.client.post(
        f"{C}/merge",
        json={"items": [
            {"product_id": "p-a", "qty": 2}, {"product_id": "p-b", "qty": 99}, {"product_id": "p-zero", "qty": 1},
            {"product_id": "nao-existe", "qty": 1}, {"product_id": "p-b", "qty": 0},
        ]},
    )  # fmt: skip
    assert r.status_code == 200
    assert {i["product_id"]: i["qty"] for i in r.json()["items"]} == {"p-a": 3, "p-b": 10}
    assert (
        cart.client.post(
            f"{C}/merge", json={"items": [{"product_id": f"p{i}", "qty": 1} for i in range(51)]}
        ).status_code
        == 422
    )
