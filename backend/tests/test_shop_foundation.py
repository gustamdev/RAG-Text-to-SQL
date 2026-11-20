"""Fundação da loja (E0): tokens com aud/jti/tv, revogação, guardas de prod, índices e mascaramento de log."""

import asyncio
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.auth.security import AUD_ADMIN, AUD_SHOP, _signing_key, create_access_token, decode_access_token
from app.config import Settings, settings
from app.core.logging import mask_uri
from app.database.indexes import ensure_indexes

ME = "/api/v1/auth/me"
LOGOUT = "/api/v1/auth/logout"
OVERVIEW = "/api/v1/admin/overview"
ASK = "/api/v1/chat/questions"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signed(claims: dict, aud: str = AUD_ADMIN) -> str:
    """Assina com a chave derivada da audiência (a mesma do servidor), sem passar por create_access_token."""
    return jwt.encode(claims, _signing_key(aud), algorithm="HS256")


def test_token_without_aud_rejected(auth_db):
    _, admin = auth_db.create_admin()
    now = datetime.now(UTC)
    base = {"sub": admin["_id"], "role": "admin", "jti": "x", "tv": 0, "iat": now, "exp": now + timedelta(minutes=5)}

    # Prova de controle: com aud, a mesma assinatura vale. Sem aud, só a falta do claim derruba.
    assert decode_access_token(_signed({**base, "aud": AUD_ADMIN}), AUD_ADMIN) is not None
    no_aud = _signed(base)
    assert decode_access_token(no_aud, AUD_ADMIN) is None
    assert auth_db.client.get(ME, headers=_bearer(no_aud)).status_code == 401


def test_token_without_tv_rejected(auth_db):
    _, admin = auth_db.create_admin()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=5)
    claims = {"sub": admin["_id"], "role": "admin", "aud": AUD_ADMIN, "jti": "x", "iat": now, "exp": exp}

    token = _signed(claims)

    assert decode_access_token(token, AUD_ADMIN) is not None  # assinatura e aud corretas
    assert auth_db.client.get(ME, headers=_bearer(token)).status_code == 401


def test_jti_is_unique_per_token():
    tokens = [create_access_token("u1", "customer", aud=AUD_SHOP) for _ in range(20)]
    jtis = {decode_access_token(t, AUD_SHOP)["jti"] for t in tokens}

    assert len(jtis) == 20


def test_token_has_jti_and_wrong_aud_rejected():
    token = create_access_token("u1", "customer", aud=AUD_SHOP, token_version=3)

    claims = decode_access_token(token, AUD_SHOP)

    assert claims["jti"] and claims["tv"] == 3 and claims["aud"] == AUD_SHOP
    assert decode_access_token(token, AUD_ADMIN) is None


def test_shop_token_on_admin_401(auth_db):
    _, admin = auth_db.create_admin()
    shop_token = create_access_token(admin["_id"], "admin", aud=AUD_SHOP)

    assert auth_db.client.get(ME, headers=_bearer(shop_token)).status_code == 401
    assert auth_db.client.get(OVERVIEW, headers=_bearer(shop_token)).status_code == 401
    assert auth_db.client.post(ASK, json={"question": "oi"}, headers=_bearer(shop_token)).status_code == 401


def test_logout_revokes_old_token(auth_db):
    headers, _ = auth_db.create_admin()
    assert auth_db.client.get(ME, headers=headers).status_code == 200

    assert auth_db.client.post(LOGOUT, headers=headers).status_code == 204

    res = auth_db.client.get(ME, headers=headers)
    assert res.status_code == 401 and res.json() == {"detail": "Sessão inválida ou expirada. Entre novamente."}


def test_logout_requires_auth_and_new_login_works(auth_db):
    assert auth_db.client.post(LOGOUT).status_code == 401
    auth_db.create_admin(email="ana@teste.com")
    login = {"email": "ana@teste.com", "password": "senha-forte-1"}
    old = auth_db.client.post("/api/v1/auth/login", json=login).json()["access_token"]
    auth_db.client.post(LOGOUT, headers=_bearer(old))

    new = auth_db.client.post("/api/v1/auth/login", json=login).json()["access_token"]

    assert auth_db.client.get(ME, headers=_bearer(old)).status_code == 401
    assert auth_db.client.get(ME, headers=_bearer(new)).status_code == 200


_PROD = {
    "_env_file": None,
    "ENV": "prod",
    "JWT_SECRET": "j" * 32,
    "MAIL_BACKEND": "smtp",
    "SMTP_HOST": "smtp.exemplo.com",
    "SMTP_FROM": "loja@exemplo.com",
    "SMTP_USER": "loja",
    "OTP_PEPPER": "o" * 32,
    "PSEUDONYM_KEY": "p" * 32,
}


def test_prod_settings_valid_baseline():
    assert Settings(**_PROD).is_prod


def test_mail_console_in_prod_fails_startup():
    with pytest.raises(ValidationError, match="MAIL_BACKEND"):
        Settings(**{**_PROD, "MAIL_BACKEND": "console"})


def test_unknown_env_fails_startup():
    with pytest.raises(ValidationError, match="ENV"):
        Settings(_env_file=None, ENV="production", JWT_SECRET="j" * 32)


@pytest.mark.parametrize("name", ["SMTP_HOST", "SMTP_FROM", "SMTP_USER"])
def test_smtp_requires_host_from_user(name):
    with pytest.raises(ValidationError, match=name):
        Settings(**{**_PROD, name: ""})


def test_ephemeral_secrets_with_many_workers_warn(caplog):
    with caplog.at_level("WARNING"):
        Settings(_env_file=None, ENV="local", JWT_SECRET="j" * 32, WEB_CONCURRENCY=4)

    assert any("WEB_CONCURRENCY=4" in r.getMessage() and "OTP_PEPPER" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("name", ["OTP_PEPPER", "PSEUDONYM_KEY"])
@pytest.mark.parametrize("value", ["", "curto"])
def test_prod_requires_long_shop_secrets(name, value):
    with pytest.raises(ValidationError, match=name):
        Settings(**{**_PROD, name: value})


def test_non_prod_empty_shop_secrets_become_ephemeral():
    cfg = Settings(_env_file=None, ENV="local", JWT_SECRET="j" * 32)

    assert len(cfg.OTP_PEPPER.get_secret_value()) >= 32 and len(cfg.PSEUDONYM_KEY.get_secret_value()) >= 32
    assert cfg.MAIL_BACKEND == "console"


def test_shop_indexes_created_and_idempotent():
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient()["idx_test"]

    async def run():
        await ensure_indexes(db)
        await ensure_indexes(db)
        return {c: await db[c].index_information() for c in await db.list_collection_names()}

    info = asyncio.run(run())

    def find(col, *fields):
        (idx,) = [i for i in info[col].values() if tuple(k for k, _ in i["key"]) == fields]
        return idx

    for col, fields in {
        "shop_customers": ("email",),
        "shop_otp": ("email", "purpose"),
        "shop_carts": ("customer_id",),
        "shop_products": ("product_id",),
        "shop_orders": ("order_id",),
        "shop_payments": ("order_id",),
        "shop_idempotency": ("customer_id", "scope", "key"),
    }.items():
        assert find(col, *fields).get("unique") is True, (col, fields)
    for col, fields in [
        ("shop_orders", ("state", "reservation_expires_at")),
        ("shop_orders", ("payment_id",)),
        ("shop_payments", ("payment_id",)),
    ]:
        assert not find(col, *fields).get("unique"), (col, fields)
    for col, field, seconds in [
        ("shop_otp", "expires_at", 0),
        ("shop_carts", "updated_at", settings.SHOP_CART_TTL_DAYS * 86400),
        ("shop_idempotency", "created_at", 86400),
        ("shop_audit", "created_at", 365 * 86400),
        ("shop_audit", "expires_at", 0),
    ]:
        assert find(col, field).get("expireAfterSeconds") == seconds, col


def test_ttl_option_conflict_applies_collmod_and_never_raises():
    from pymongo.errors import OperationFailure

    class FakeCol:
        async def create_index(self, spec, **opts):
            if "expireAfterSeconds" in opts:
                raise OperationFailure("conflict", code=85)

    class FakeDb:
        commands: list = []

        def __getitem__(self, _):
            return FakeCol()

        async def command(self, cmd):
            self.commands.append(cmd)

    db = FakeDb()
    asyncio.run(ensure_indexes(db))

    audit = {"keyPattern": {"created_at": 1}, "expireAfterSeconds": 365 * 86400}
    assert {"collMod": "shop_audit", "index": audit} in db.commands


def test_mask_uri_hides_credentials():
    assert mask_uri("mongodb://app:s3nha@host:27017/db") == "mongodb://***@host:27017/db"
    assert mask_uri("mongodb://localhost:27017") == "mongodb://localhost:27017"
    masked = mask_uri("mongodb://app:p@ss:w@rd@host:27017/db?authSource=admin")
    assert masked == "mongodb://***@host:27017/db?authSource=admin" and "ss" not in masked and "app" not in masked


def test_cors_preflight_allows_patch_and_delete_on_shop_cart(client):
    res = client.options(
        "/api/v1/shop/cart",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PATCH"},
    )
    assert res.status_code == 200
    allowed = res.headers["access-control-allow-methods"]
    assert "PATCH" in allowed and "DELETE" in allowed


def test_login_burst_counts_ip_key_before_await_and_success_resets():
    from app.core.errors import TooManyRequests, Unauthorized
    from app.core.rate_limit import FailureLimiter
    from app.schemas.auth import LoginRequest
    from app.services import auth_service

    class NoUsers:
        async def get_by_email(self, _email):
            return None

    limiter = FailureLimiter(max_failures=3, window_s=60)
    req = LoginRequest(email="a@teste.com", password="senha-errada-123")

    async def burst():
        return await asyncio.gather(
            *(auth_service.login(NoUsers(), limiter, req, "1.1.1.1") for _ in range(6)), return_exceptions=True
        )

    results = asyncio.run(burst())

    # A falha de e-mail|IP é contada antes do await: a rajada paralela já esbarra no limite (3).
    assert [type(r) for r in results] == [Unauthorized] * 3 + [TooManyRequests] * 3
    assert limiter.count("a@teste.com|1.1.1.1") == 3
