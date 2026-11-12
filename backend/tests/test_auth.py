import time

import pytest

from app.auth.security import create_access_token, decode_access_token, hash_password, verify_password
from app.core.rate_limit import FailureLimiter, SlidingWindowLimiter

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def test_password_hash_roundtrip():
    stored = hash_password("senha-forte-1")
    assert stored != "senha-forte-1" and stored.startswith("$argon2")
    assert verify_password("senha-forte-1", stored)
    assert not verify_password("outra", stored)
    assert not verify_password("dummy-password-for-timing", None)  # conta inexistente nunca autentica


def test_token_tamper_and_garbage_rejected():
    token = create_access_token("u1", "admin")
    assert decode_access_token(token)["sub"] == "u1"
    assert decode_access_token(token[:-2] + "xx") is None
    assert decode_access_token("lixo") is None


def test_failure_limiter_blocks_and_resets():
    limiter = FailureLimiter(max_failures=2, window_s=60)
    limiter.register_failure("k")
    assert not limiter.is_blocked("k")
    limiter.register_failure("k")
    assert limiter.is_blocked("k")
    limiter.reset("k")
    assert not limiter.is_blocked("k")


def test_failure_limiter_window_expires():
    limiter = FailureLimiter(max_failures=1, window_s=0.05)
    limiter.register_failure("k")
    assert limiter.is_blocked("k")
    time.sleep(0.08)
    assert not limiter.is_blocked("k")


def test_sliding_window_limiter_counts_every_event_per_key():
    limiter = SlidingWindowLimiter(max_events=2, window_s=60)
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.allow("b")  # outra chave tem a própria cota


def test_sliding_window_limiter_window_expires():
    limiter = SlidingWindowLimiter(max_events=1, window_s=0.05)
    assert limiter.allow("k")
    assert not limiter.allow("k")
    time.sleep(0.08)
    assert limiter.allow("k")


def test_login_ok_returns_token_and_user_without_secrets(auth_db):
    auth_db.create_admin(email="ana@teste.com")

    res = auth_db.client.post(LOGIN, json={"email": "ANA@teste.com", "password": "senha-forte-1"})

    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["user"]["role"] == "admin" and body["user"]["email"] == "ana@teste.com"
    assert set(body["user"]) == {"id", "name", "email", "role", "created_at"}
    assert "password" not in str(body)


def test_login_token_opens_me(auth_db):
    auth_db.create_admin(email="ana@teste.com")
    token = auth_db.client.post(LOGIN, json={"email": "ana@teste.com", "password": "senha-forte-1"}).json()[
        "access_token"
    ]

    res = auth_db.client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200 and res.json()["email"] == "ana@teste.com"


def test_wrong_password_and_unknown_email_are_identical(auth_db):
    auth_db.create_admin(email="ana@teste.com")

    wrong = auth_db.client.post(LOGIN, json={"email": "ana@teste.com", "password": "errada"})
    unknown = auth_db.client.post(LOGIN, json={"email": "nao@existe.com", "password": "errada"})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "E-mail ou senha incorretos."}
    assert wrong.headers["www-authenticate"] == "Bearer"


def test_non_admin_login_is_the_same_generic_401(auth_db):
    auth_db.create_non_admin(email="comprador@teste.com")
    auth_db.create_admin(email="ana@teste.com")

    non_admin = auth_db.client.post(LOGIN, json={"email": "comprador@teste.com", "password": "senha-forte-1"})
    wrong = auth_db.client.post(LOGIN, json={"email": "ana@teste.com", "password": "errada"})

    # Senha certa de conta sem perfil admin não entra e não se distingue de senha errada.
    assert non_admin.status_code == 401
    assert non_admin.json() == wrong.json()


def test_non_admin_login_counts_toward_rate_limit(auth_db):
    auth_db.create_non_admin(email="comprador@teste.com")
    body = {"email": "comprador@teste.com", "password": "senha-forte-1"}

    codes = [auth_db.client.post(LOGIN, json=body).status_code for _ in range(6)]

    assert codes == [401] * 5 + [429]


def test_login_rate_limited_after_repeated_failures(auth_db):
    auth_db.create_admin(email="ana@teste.com")
    body = {"email": "ana@teste.com", "password": "errada"}

    codes = [auth_db.client.post(LOGIN, json=body).status_code for _ in range(6)]

    assert codes[:5] == [401] * 5 and codes[5] == 429
    # Mesmo a senha certa fica bloqueada durante a janela.
    good = auth_db.client.post(LOGIN, json={"email": "ana@teste.com", "password": "senha-forte-1"})
    assert good.status_code == 429


@pytest.mark.parametrize(
    "payload",
    [{"email": "invalido", "password": "x"}, {"email": "a@b.com", "password": ""}, {"email": "a@b.com"}, {}],
)
def test_login_validation(auth_db, payload):
    assert auth_db.client.post(LOGIN, json=payload).status_code == 422


def test_register_endpoint_does_not_exist(auth_db):
    res = auth_db.client.post(
        "/api/v1/auth/register", json={"name": "Ana", "email": "a@b.com", "password": "senha-forte-1"}
    )
    assert res.status_code in (404, 405)


def test_me_requires_valid_token(auth_db):
    assert auth_db.client.get(ME).status_code == 401
    assert auth_db.client.get(ME, headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_me_for_deleted_user_is_401(auth_db):
    headers, user = auth_db.create_admin()
    auth_db.run(auth_db.db["users"].delete_one({"_id": user["_id"]}))

    assert auth_db.client.get(ME, headers=headers).status_code == 401


def test_me_with_unknown_role_is_403(auth_db):
    # Conta legada com papel que não existe mais: o token é válido, mas o papel não dá acesso.
    headers, _ = auth_db.create_non_admin()

    res = auth_db.client.get("/api/v1/admin/overview", headers=headers)

    assert res.status_code == 403


def test_users_email_index_is_unique(auth_db):
    from pymongo.errors import DuplicateKeyError

    auth_db.create_admin(email="ana@teste.com")

    with pytest.raises(DuplicateKeyError):
        auth_db.create_admin(email="ana@teste.com")
