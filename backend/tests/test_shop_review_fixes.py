"""Correções da revisão: claim de idempotência, limite de page, photos_qty e índices de ordenação."""

import asyncio

from mongomock_motor import AsyncMongoMockClient
from shop_helpers import V1, shop  # noqa: F401

from app.database.indexes import ensure_indexes
from app.database.repos.shop_idempotency import ShopIdempotencyRepo
from app.database.repos.shop_products import SORTS
from app.services.shop_catalog import card


def test_claim_retries_when_owner_releases_between_duplicate_and_find():
    async def go():
        db = AsyncMongoMockClient()["t"]
        await ensure_indexes(db)  # o índice único é o que gera o DuplicateKeyError
        repo = ShopIdempotencyRepo(db)
        assert (await repo.claim("c", "checkout", "k", "h"))[0] is None
        real, calls = repo.col.find_one, []

        async def racy(*a, **kw):  # dono libera a chave exatamente aqui
            calls.append(1)
            await repo.col.delete_many({})
            return await real(*a, **kw)

        repo.col.find_one = racy
        return await repo.claim("c", "checkout", "k", "h"), calls

    (existing, token), calls = asyncio.run(go())
    assert existing is None and token and calls == [1]  # 2ª volta reservou


def test_orders_page_has_upper_bound(shop):  # noqa: F811
    shop.login("cust")
    assert shop.client.get(f"{V1}/shop/orders?page=100001").status_code == 422
    assert shop.client.get(f"{V1}/shop/orders?page=100000").status_code == 200


def test_photos_qty_zero_or_none_becomes_one():
    base = {"product_id": "p", "title": "t", "category": "c", "category_label": "C", "price_cents": 1, "stock": 1}
    assert card({**base, "photos_qty": 0}).photos_qty == 1
    assert card({**base, "photos_qty": None}).photos_qty == 1
    assert card(base).photos_qty == 1
    assert card({**base, "photos_qty": 4}).photos_qty == 4


def test_sort_and_admin_indexes_exist_and_are_idempotent():
    async def go():
        db = AsyncMongoMockClient()["t"]
        await ensure_indexes(db)
        await ensure_indexes(db)
        prod = [i["key"] for i in (await db["shop_products"].index_information()).values()]
        orders = [i["key"] for i in (await db["shop_orders"].index_information()).values()]
        return prod, orders

    prod, orders = asyncio.run(go())
    for order in SORTS.values():
        assert [*order, ("product_id", 1)] in prod
    assert [("created_at", 1)] in orders


def test_ip_key_groups_ipv6_by_64_and_keeps_ipv4():
    from app.core.rate_limit import ip_key

    assert ip_key("2001:db8:1:2:aaaa::1") == ip_key("2001:db8:1:2:bbbb::9") == "2001:db8:1:2::"
    assert ip_key("2001:db8:1:3::1") != ip_key("2001:db8:1:2::1")
    assert ip_key("1.2.3.4") == "1.2.3.4" and ip_key("unknown") == "unknown"


def test_ip_limiter_counts_ipv6_rotation_as_one_client():
    from types import SimpleNamespace

    from app.api.deps import _ip_limit
    from app.core.errors import TooManyRequests

    req = lambda host: SimpleNamespace(app=app_ns, client=SimpleNamespace(host=host))  # noqa: E731
    app_ns = SimpleNamespace(state=SimpleNamespace())
    _ip_limit(req("2001:db8::1"), "t_limiter", 2)
    _ip_limit(req("2001:db8::2"), "t_limiter", 2)
    try:
        _ip_limit(req("2001:db8::ffff"), "t_limiter", 2)
    except TooManyRequests:
        return
    raise AssertionError("3rd address of the same /64 must be limited")


def test_access_log_masks_zip_in_freight_query():
    import logging

    from app.core.logging import MaskZipFilter

    for path in ("/api/v1/shop/cart/freight?zip=01310100", "/api/v1/shop/products/abc/freight?x=1&zip=01310-100"):
        rec = logging.LogRecord("a", 20, "", 0, '%s - "%s %s HTTP/%s" %d', ("1.2.3.4", "GET", path, "1.1", 200), None)
        MaskZipFilter().filter(rec)
        assert "01310" not in rec.getMessage() and "zip=XXXXX***" in rec.getMessage()


def test_retention_repeats_cleanup_of_deleted_account_with_leftovers():
    from app.api.shop_deps import SnapshotRefresher
    from app.core.timeutil import now
    from app.services.shop_retention import ShopRetention

    async def go():
        db = AsyncMongoMockClient()["t"]
        await db["shop_customers"].insert_many([
            {"_id": "gone", "email": "deleted-gone@anon.invalid", "deleted_at": now()},
            {"_id": "clean", "email": "deleted-clean@anon.invalid", "deleted_at": now()},
        ])  # fmt: skip
        await db["shop_addresses"].insert_one({"_id": "a1", "customer_id": "gone", "zip": "01310100"})
        await db["shop_carts"].insert_one({"customer_id": "gone", "items": []})
        await db["shop_orders"].insert_one(
            {"order_id": "o1", "customer_id": "gone", "state": "paid", "address": {"zip": "01310100"},
             "created_at": now()}
        )  # fmt: skip
        counts = await ShopRetention(db, SnapshotRefresher()).run()
        left = [await db[c].count_documents({"customer_id": "gone"}) for c in ("shop_addresses", "shop_carts")]
        order = await db["shop_orders"].find_one({"order_id": "o1"})
        return counts, left, order["address"]["zip"]

    counts, left, zip_ = asyncio.run(go())
    assert counts["cleanups"] == 1 and left == [0, 0] and zip_ is None


def test_address_city_state_come_from_zip_lookup_not_from_client(shop):  # noqa: F811
    from app.api.routes.shop_zip import get_zip_remote
    from app.schemas.shop_store import ZipOut

    class Remote:
        async def fetch(self, zip8):
            return ZipOut(zip=zip8, city="São Paulo", state="SP", source="brasilapi") if zip8 == "01310100" else None

    shop.client.app.dependency_overrides[get_zip_remote] = Remote
    shop.login("cust")
    body = {"label": "Casa", "recipient": "Ana", "zip": "01310100", "street": "Av. Paulista", "number": "1",
            "district": "Bela Vista", "city": "Manaus", "state": "AM"}  # fmt: skip
    created = shop.client.post(f"{V1}/shop/account/addresses", json=body)
    assert created.status_code == 201 and (created.json()["city"], created.json()["state"]) == ("São Paulo", "SP")

    # CEP desconhecido: mantém o digitado
    other = shop.client.post(f"{V1}/shop/account/addresses", json={**body, "zip": "69000000"})
    assert other.json()["state"] == "AM"

    # PATCH só da UF: reconsulta pelo CEP salvo e corrige
    patched = shop.client.patch(f"{V1}/shop/account/addresses/{created.json()['id']}", json={"state": "RJ"})
    assert patched.status_code == 200 and patched.json()["state"] == "SP"


def test_initial_stock_rule_is_deterministic_and_realistic():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import seed_shop

    ids = [f"{i:032x}" for i in range(5000)]
    stocks = [seed_shop.initial_stock(i, 1) for i in ids]
    assert stocks == [seed_shop.initial_stock(i, 1) for i in ids]  # determinístico
    zero = sum(s == 0 for s in stocks) / len(stocks)
    low = sum(1 <= s <= 5 for s in stocks) / len(stocks)
    assert 0.005 < zero < 0.04 and 0.05 < low < 0.2
    assert all(0 <= s <= 150 for s in stocks) and all(s >= 15 for s in stocks if s > 5)
    assert max(seed_shop.initial_stock(i, 100) for i in ids) <= 150


def test_seed_restock_flag_overwrites_only_when_asked():
    import sys
    from pathlib import Path

    import mongomock

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import seed_shop

    db = mongomock.MongoClient()["t"]
    db["products"].insert_one({"product_id": "p" * 32, "product_category_name": "x"})
    db["order_items"].insert_one({"order_id": "o", "product_id": "p" * 32, "price": 10.0})
    seed_shop.seed(db)
    expected = seed_shop.initial_stock("p" * 32, 1)
    assert db["shop_products"].find_one()["stock"] == expected
    db["shop_products"].update_one({}, {"$set": {"stock": 999}})
    seed_shop.seed(db)
    assert db["shop_products"].find_one()["stock"] == 999  # reexecutar não mexe
    seed_shop.seed(db, restock=True)
    assert db["shop_products"].find_one()["stock"] == expected
