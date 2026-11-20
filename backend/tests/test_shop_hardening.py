"""Correções das revisões de E1-E4: OTP/limites persistidos, rate limit, índices, catálogo, corridas, PII."""

import asyncio
import logging
import sys
from pathlib import Path

import mongomock
import pytest
from mongomock_motor import AsyncMongoMockClient
from shop_helpers import V1, shop  # noqa: F401

from app.api.shop_deps import get_current_customer
from app.config import settings
from app.core.errors import BadRequest, Conflict, TooManyRequests, Unauthorized
from app.core.rate_limit import FailureLimiter
from app.database.indexes import ensure_indexes
from app.database.repos.shop_addresses import ShopAddressRepo
from app.database.repos.shop_carts import ShopCartRepo
from app.database.repos.shop_otp import ShopOtpRepo
from app.database.repos.shop_products import ShopProductRepo
from app.schemas.shop_auth import ResendOtpRequest, ShopLoginRequest, SignupRequest, VerifyOtpRequest
from app.schemas.shop_store import AddressIn
from app.services import mail
from app.services import shop_auth_service as sas
from app.services.shop_addresses import ShopAddresses
from app.services.shop_auth_service import ShopAuthService
from app.services.shop_cart import ShopCart

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed_shop  # noqa: E402

PW = "senha-bem-longa-1"
X = "x@exemplo.com"


class Env:
    """Serviço de identidade sobre mongomock; `spawn` captura (email, code, purpose) em vez de enviar."""

    def __init__(self, monkeypatch):
        monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_S", 0)
        monkeypatch.setattr(settings, "OTP_MAX_SENDS_PER_HOUR", 3)
        self.db = AsyncMongoMockClient()["h"]
        self.svc = ShopAuthService(self.db)
        self.sent: list[tuple] = []

    def spawn(self, _fn, *args):
        self.sent.append(args)

    def code(self, purpose):
        return [c for _, c, p in self.sent if p == purpose][-1]

    @staticmethod
    def signup_req(email=X, password=PW):
        return SignupRequest(email=email, password=password, accept_terms=True, accept_adult=True, terms_version="2")

    async def signup(self, email=X, password=PW, ip="1.1.1.1"):
        return await self.svc.signup(self.signup_req(email, password), ip, self.spawn)

    async def register(self, email=X, ip="1.1.1.1"):
        await self.signup(email, ip=ip)
        await self.svc.verify_signup(VerifyOtpRequest(email=email, code=self.code("signup")), ip)

    async def login(self, password=PW, ip="1.1.1.1", email=X):
        return await self.svc.login(ShopLoginRequest(email=email, password=password), ip, self.spawn)


@pytest.fixture
def env(monkeypatch):
    return Env(monkeypatch)


def wrong(code):
    return "000000" if code != "000000" else "111111"


# --- 1. pré-sequestro por re-signup ------------------------------------------------------------


def test_resignup_with_live_otp_keeps_password_and_resends(env):
    async def run():
        await env.signup(password=PW)
        await env.signup(password="outra-senha-longa-2")
        assert len(env.sent) == 2  # reenviou
        await env.svc.verify_signup(VerifyOtpRequest(email=X, code=env.code("signup")), "1.1.1.1")
        await env.login(PW)  # senha original vale
        with pytest.raises(Unauthorized):
            await env.login("outra-senha-longa-2")

    asyncio.run(run())


def test_resignup_after_otp_expired_replaces_pending(env):
    async def run():
        await env.signup(password=PW)
        await env.db["shop_otp"].delete_many({"purpose": "signup"})
        await env.signup(password="outra-senha-longa-2")
        await env.svc.verify_signup(VerifyOtpRequest(email=X, code=env.code("signup")), "1.1.1.1")
        await env.login("outra-senha-longa-2")

    asyncio.run(run())


# --- 2. cotas de OTP ---------------------------------------------------------------------------


def test_anonymous_signups_do_not_block_legit_login(env):
    async def run():
        await env.register()  # 1 envio no balde de cadastro
        await env.signup(ip="2.2.2.2")
        await env.signup(ip="3.3.3.3")  # 3 no balde de cadastro: esgotado
        with pytest.raises(TooManyRequests):
            await env.signup(ip="4.4.4.4")
        assert (await env.login()).masked_email == "x***@exemplo.com"

    asyncio.run(run())


def test_otp_wrong_guesses_from_ip_a_do_not_burn_ip_b(env):
    async def run():
        await env.signup()
        good = env.code("signup")
        for _ in range(settings.OTP_MAX_ATTEMPTS):
            with pytest.raises(BadRequest):
                await env.svc.verify_signup(VerifyOtpRequest(email=X, code=wrong(good)), "9.9.9.9")
        with pytest.raises(BadRequest):  # o IP A está esgotado, até com o código certo
            await env.svc.verify_signup(VerifyOtpRequest(email=X, code=good), "9.9.9.9")
        token = await env.svc.verify_signup(VerifyOtpRequest(email=X, code=good), "1.1.1.1")
        assert token.customer.email == X

    asyncio.run(run())


def test_login_429_does_not_depend_on_password(env, monkeypatch):
    async def run():
        await env.register()
        monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_S", 60)
        await env.login()  # consome o cooldown de login
        for pw in (PW, "senha-errada-123"):
            with pytest.raises(TooManyRequests):
                await env.login(pw)

    asyncio.run(run())


# --- 3. limite de login persistido -------------------------------------------------------------


def test_login_limits_survive_10k_keys_flood(env, monkeypatch):
    async def run():
        await env.register()
        for _ in range(settings.LOGIN_MAX_FAILURES):
            with pytest.raises(Unauthorized):
                await env.login("senha-errada-123", ip="7.7.7.7")
        flood = [
            {"_id": f"f{i}", "email": f"flood{i}", "purpose": "rate_login_pair", "n": 1, "code_hash": None}
            for i in range(10_000)
        ]
        await env.db["shop_otp"].insert_many(flood)
        with pytest.raises(TooManyRequests):  # contadores vivos: o flood não os evictou
            await env.login("senha-errada-123", ip="7.7.7.7")
        real = await env.db["shop_otp"].find({"purpose": "rate_login_pair", "n": {"$gte": 5}}).to_list(None)
        assert "7.7.7.7" not in str(real) and X not in str(real)

    monkeypatch.setattr(sas.asyncio, "sleep", lambda _s: asyncio.sleep(0))
    asyncio.run(run())


def test_login_counters_pseudonymous_and_reset_on_success(env, monkeypatch):
    async def run():
        await env.register()
        with pytest.raises(Unauthorized):
            await env.login("senha-errada-123")
        docs = await env.db["shop_otp"].find({"purpose": {"$regex": "^rate_login"}}).to_list(None)
        assert {d["purpose"] for d in docs} == {"rate_login_email", "rate_login_ip", "rate_login_pair"}
        assert "1.1.1.1" not in str(docs) and "exemplo" not in str(docs)
        await env.login()
        rest = await env.db["shop_otp"].find({"purpose": {"$regex": "^rate_login"}}).to_list(None)
        assert {d["purpose"] for d in rest} == {"rate_login_ip"}

    monkeypatch.setattr(sas.asyncio, "sleep", lambda _s: asyncio.sleep(0))
    asyncio.run(run())


def test_failure_limiter_evicts_oldest_when_full():
    lim = FailureLimiter(max_failures=3, window_s=60, max_keys=3)
    for k in "abc":
        lim.register_failure(k)
    lim.register_failure("a")
    assert lim.count("a") == 2  # chave existente não evicta
    lim.register_failure("new")  # cheia: a mais antiga ("a", inserida primeiro) sai
    assert lim.count("new") == 1 and lim.count("a") == 0 and lim.count("b") == 1
    lim2 = FailureLimiter(max_failures=3, window_s=0.01, max_keys=2)
    lim2.register_failure("a")
    lim2.register_failure("b")
    import time

    time.sleep(0.02)
    lim2.register_failure("c")  # expiradas liberam espaço
    assert lim2.count("c") == 1 and len(lim2._failures) == 1


# --- 4. rate limit -----------------------------------------------------------------------------


def test_customer_rate_limit_121st_is_429(shop):  # noqa: F811
    shop.login("cust-a")
    codes = [shop.client.get(f"{V1}/shop/account/addresses").status_code for _ in range(121)]
    assert codes[:120] == [200] * 120 and codes[120] == 429
    shop.login("cust-b")  # outro cliente tem a própria cota
    assert shop.client.get(f"{V1}/shop/account/addresses").status_code == 200


def test_catalog_and_auth_have_separate_ip_buckets(shop, monkeypatch):  # noqa: F811
    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT", 4)
    assert [shop.client.get(f"{V1}/shop/products/categories").status_code for _ in range(5)][-1] == 429
    body = {"email": "a@exemplo.com", "code": "123456"}
    assert shop.client.post(f"{V1}/shop/auth/verify-otp", json=body).status_code == 400  # balde de auth intacto


# --- 5. índices e TTL de conta pendente --------------------------------------------------------


def test_new_indexes_and_pending_ttl():
    db = AsyncMongoMockClient()["i"]

    async def run():
        await ensure_indexes(db)
        cols = ("geolocation", "shop_products", "shop_customers", "shop_carts")
        return {c: await db[c].index_information() for c in cols}

    info = asyncio.run(run())
    keys = lambda col: {tuple(k for k, _ in i["key"]): i for i in info[col].values()}  # noqa: E731
    assert ("geolocation_zip_code_prefix",) in keys("geolocation")
    for f in ("units_sold", "price_cents", "avg_rating", "category"):
        assert (f,) in keys("shop_products")
    assert keys("shop_customers")[("pending_expires_at",)]["expireAfterSeconds"] == 0
    assert keys("shop_carts")[("updated_at",)]["expireAfterSeconds"] == settings.SHOP_CART_TTL_DAYS * 86400


def test_signup_sets_pending_expiry_and_verify_removes_it(env):
    async def run():
        await env.signup()
        doc = await env.db["shop_customers"].find_one({"email": X})
        assert doc["pending_expires_at"] is not None
        await env.svc.verify_signup(VerifyOtpRequest(email=X, code=env.code("signup")), "1.1.1.1")
        assert "pending_expires_at" not in await env.db["shop_customers"].find_one({"email": X})

    asyncio.run(run())


# --- 6. catálogo -------------------------------------------------------------------------------


def test_suggest_cached_categories_and_anchored_prefix(shop):  # noqa: F811
    shop.product("aaaa0001", title="Cama mesa banho · Modelo A")
    shop.product("bbbb0002", title="Outro · Cama", category="x", category_label="Esporte")
    calls = []
    orig = ShopProductRepo.categories

    async def counting(self):
        calls.append(1)
        return await orig(self)

    ShopProductRepo.categories = counting
    try:
        for _ in range(100):
            body = shop.client.get(f"{V1}/shop/products/suggest", params={"q": "cama"}).json()
    finally:
        ShopProductRepo.categories = orig
    assert len(calls) == 1
    assert [p["product_id"] for p in body["products"]] == ["aaaa0001"]  # "Cama" no meio do título não casa
    assert shop.client.get(f"{V1}/shop/products/suggest", params={"q": ".*"}).json()["products"] == []


# --- 7. validação ------------------------------------------------------------------------------

ARABIC_ZIP = "٠١٣١٠٠٠١"


def test_arabic_digits_and_overflow_are_422(shop):  # noqa: F811
    shop.login("cust-a")
    assert shop.client.get(f"{V1}/shop/products/x/freight", params={"zip": ARABIC_ZIP}).status_code == 422
    assert shop.client.get(f"{V1}/shop/cart/freight", params={"zip": ARABIC_ZIP}).status_code == 422
    assert shop.client.post(f"{V1}/shop/cart/freight", json={"zip": ARABIC_ZIP}).status_code == 422
    addr = {"label": "Casa", "zip": ARABIC_ZIP, "city": "SP", "state": "SP"}
    assert shop.client.post(f"{V1}/shop/account/addresses", json=addr).status_code == 422
    body = {"email": "a@exemplo.com", "code": "١٢٣٤٥٦"}
    assert shop.client.post(f"{V1}/shop/auth/verify-otp", json=body).status_code == 422
    for p in ("min_price_cents", "max_price_cents", "min_reviews"):
        assert shop.client.get(f"{V1}/shop/products", params={p: 10**9 + 1}).status_code == 422
        assert shop.client.get(f"{V1}/shop/products", params={p: 10**9}).status_code == 200


# --- 8/11. corridas ----------------------------------------------------------------------------


def _slow(cls, name):
    """Cede o loop após a leitura: força o intercalar que o mongomock (síncrono) esconderia."""
    orig = getattr(cls, name)

    async def wrapper(self, *a, **k):
        res = await orig(self, *a, **k)
        await asyncio.sleep(0)
        return res

    setattr(cls, name, wrapper)
    return lambda: setattr(cls, name, orig)


def test_address_limit_and_single_default_under_concurrency(monkeypatch):
    db = AsyncMongoMockClient()["a"]
    undo = [_slow(ShopAddressRepo, "count"), _slow(ShopAddressRepo, "for_customer")]
    svc = ShopAddresses(ShopAddressRepo(db))

    def body(i):
        return AddressIn(label=f"c{i}", zip="01310100", city="SP", state="SP", is_default=True)

    async def run():
        res = await asyncio.gather(*(svc.create("c1", body(i)) for i in range(6)), return_exceptions=True)
        rows = await svc.all("c1")
        return res, rows

    try:
        res, rows = asyncio.run(run())
    finally:
        for u in undo:
            u()
    assert len(rows) <= settings.SHOP_MAX_ADDRESSES
    assert all(isinstance(r, Conflict) for r in res if isinstance(r, Exception))
    assert sum(r.is_default for r in rows) == 1


def test_cart_add_and_merge_concurrent_do_not_lose_items(shop):  # noqa: F811
    shop.product("p-a", stock=50)
    shop.run(shop.db["shop_carts"].create_index("customer_id", unique=True))  # como em ensure_indexes
    undo = _slow(ShopCartRepo, "get")
    cart = ShopCart(ShopCartRepo(shop.db), ShopProductRepo(shop.db))

    async def run():
        await asyncio.gather(*(cart.add("c1", "p-a", 1) for _ in range(5)))
        await asyncio.gather(*(cart.merge("c1", [("p-a", 1)]) for _ in range(3)))
        return await cart.get("c1")

    try:
        out = asyncio.run(run())
    finally:
        undo()
    assert out.items[0].qty == 8


def test_otp_consume_and_allow_send_are_atomic_under_gather():
    db = AsyncMongoMockClient()["o"]
    repo = ShopOtpRepo(db)

    async def run():
        await repo.issue("e", "login", "h", 300)
        used = await asyncio.gather(*(repo.consume("e", "login", "h", 20, 5, "ip") for _ in range(5)))
        sends = await asyncio.gather(*(repo.allow_send("k", "rate_email", 3, 0) for _ in range(10)))
        return used, sends

    used, sends = asyncio.run(run())
    assert used.count(True) == 1 and sends.count(True) == 3


# --- 9. logs e auditoria -----------------------------------------------------------------------


def test_otp_delivery_failure_logs_only_exception_type(env, monkeypatch, caplog):
    def boom(email, code, purpose):
        raise RuntimeError(f"smtp recusou {email} codigo {code}")

    monkeypatch.setattr(mail, "send_otp", boom)
    with caplog.at_level(logging.DEBUG):
        asyncio.run(sas._deliver(X, "123456", "login"))
    assert "RuntimeError" in caplog.text and "@" not in caplog.text and "123456" not in caplog.text
    assert all(r.exc_info is None for r in caplog.records)


def test_audit_ip_only_on_risk_events_truncated_and_terms_event(env):
    async def run():
        await env.register(ip="203.0.113.7")
        with pytest.raises(Unauthorized):
            await env.login("senha-errada-123", ip="203.0.113.99")
        await env.login(ip="203.0.113.7")
        await env.svc.verify_login(VerifyOtpRequest(email=X, code=env.code("login")), "203.0.113.7")
        return await env.db["shop_audit"].find({}).to_list(None)

    audit = asyncio.run(run())
    by_event = {}
    for a in audit:
        by_event.setdefault(a["event"], []).append(a)
    for ev in ("signup", "login_ok", "terms_accepted"):
        assert all(a["ip_hmac"] is None for a in by_event[ev]), ev
    assert by_event["terms_accepted"][0]["meta"] == {"version": "2"}
    assert by_event["login_fail"][0]["ip_hmac"] and by_event["otp_sent"][0]["ip_hmac"]
    assert sas.pseudo(f"ip:{sas._ip_net('203.0.113.7')}") == sas.pseudo(f"ip:{sas._ip_net('203.0.113.99')}")
    assert sas._ip_net("203.0.113.99") == "203.0.113.0/24"


# --- 10. seed ----------------------------------------------------------------------------------


def test_seed_created_at_is_stable_per_product():
    from datetime import datetime

    p1 = "p1" + "0" * 30
    db = mongomock.MongoClient()["olist"]
    db["products"].insert_many([{"product_id": "p1" + "0" * 30}, {"product_id": "p2" + "0" * 30}])
    db["order_items"].insert_many(
        [
            {"order_id": "o1", "product_id": p1, "price": 10.0, "shipping_limit_date": datetime(2018, 5, 2)},
            {"order_id": "o2", "product_id": p1, "price": 10.0, "shipping_limit_date": datetime(2018, 1, 9)},
            {"order_id": "o3", "product_id": "p2" + "0" * 30, "price": 10.0},
        ]
    )
    seed_shop.seed(db)
    first = {d["product_id"][:2]: d["created_at"] for d in db["shop_products"].find()}
    seed_shop.seed(db)
    second = {d["product_id"][:2]: d["created_at"] for d in db["shop_products"].find()}
    assert first == second
    assert first["p1"].replace(tzinfo=None) == datetime(2018, 1, 9)
    assert first["p2"].replace(tzinfo=None) == datetime(2017, 1, 1)


# --- 11. dependência real ----------------------------------------------------------------------


def test_real_get_current_customer_works_on_cart_routes(auth_db, monkeypatch):
    sent = []
    monkeypatch.setattr(mail, "send_otp", lambda e, c, p: sent.append(c))
    c = auth_db.client
    body = {
        "email": X, "password": PW, "accept_terms": True, "accept_adult": True, "terms_version": "2", "nickname": "X",
    }  # fmt: skip
    assert c.post(f"{V1}/shop/auth/signup", json=body).status_code == 202
    token = c.post(f"{V1}/shop/auth/verify-otp", json={"email": X, "code": sent[-1]}).json()["access_token"]
    assert get_current_customer not in c.app.dependency_overrides  # dependência REAL
    h = {"Authorization": f"Bearer {token}"}
    assert c.get(f"{V1}/shop/cart").status_code == 401
    res = c.get(f"{V1}/shop/cart", headers=h)
    assert res.status_code == 200 and res.json()["items"] == []
    assert c.get(f"{V1}/shop/account/addresses", headers=h).status_code == 200
    # Resend com purpose login sem senha validada continua sem enviar (balde de cadastro, sem porta lateral).
    n = len(sent)
    assert ResendOtpRequest(email=X, purpose="login")
    c.post(f"{V1}/shop/auth/resend-otp", json={"email": X, "purpose": "login"})
    assert len(sent) == n
