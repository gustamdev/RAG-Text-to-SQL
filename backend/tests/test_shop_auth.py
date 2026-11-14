"""E1: identidade do cliente da loja (cadastro, OTP, login com MFA, revogação, auditoria)."""

import pytest

from app.api.shop_deps import get_current_customer  # noqa: F401  (contrato: importável pelos outros routers)
from app.auth.security import AUD_ADMIN, AUD_SHOP, create_access_token
from app.config import settings
from app.core.timeutil import now
from app.services import mail

S = "/api/v1/shop/auth"
PW = "senha-bem-longa-1"
EMAIL = "ana@exemplo.com"
SENT = {"detail": "Se o e-mail puder ser usado, enviamos um código."}
BAD_OTP = {"detail": "Código inválido ou expirado"}


class Shop:
    def __init__(self, auth_db, sent):
        self.c, self.db, self.sent = auth_db.client, auth_db, sent

    def signup(self, email=EMAIL, password=PW, **over):
        body = {
            "nickname": "Ana",
            "email": email,
            "password": password,
            "accept_terms": True,
            "accept_adult": True,
            "terms_version": "1",
            **over,
        }
        return self.c.post(f"{S}/signup", json=body)

    def last_code(self, purpose=None):
        return [code for _, code, p in self.sent if purpose in (None, p)][-1]

    def verify(self, code=None, email=EMAIL):
        return self.c.post(f"{S}/verify-otp", json={"email": email, "code": code or self.last_code("signup")})

    def login(self, email=EMAIL, password=PW):
        return self.c.post(f"{S}/login", json={"email": email, "password": password})

    def login_verify(self, code=None, email=EMAIL):
        return self.c.post(f"{S}/login/verify-otp", json={"email": email, "code": code or self.last_code("login")})

    def register(self, email=EMAIL):
        assert self.signup(email).status_code == 202
        res = self.verify(email=email)
        assert res.status_code == 200
        return res.json()

    def docs(self, col):
        return self.db.run(self.db.db[col].find({}).to_list(None))

    @staticmethod
    def h(token):
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def shop(auth_db, monkeypatch):
    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mail, "send_otp", lambda email, code, purpose: sent.append((email, code, purpose)))
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_S", 0)
    monkeypatch.setattr(settings, "OTP_MAX_SENDS_PER_HOUR", 50)
    return Shop(auth_db, sent)


def test_full_flow_signup_verify_login_verify_me(shop):
    assert shop.signup().json() == SENT
    ver = shop.verify().json()
    assert ver["customer"]["email"] == EMAIL and ver["customer"]["nickname"] == "Ana"
    assert shop.c.get(f"{S}/me", headers=shop.h(ver["access_token"])).status_code == 200

    res = shop.login()
    assert res.status_code == 202 and res.json() == {"mfa_required": True, "masked_email": "a***@exemplo.com"}
    token = shop.login_verify().json()["access_token"]
    me = shop.c.get(f"{S}/me", headers=shop.h(token))
    assert me.status_code == 200 and me.json()["email"] == EMAIL and "password" not in me.text
    assert [p for _, _, p in shop.sent] == ["signup", "login"]


def test_signup_no_email_enumeration(shop):
    shop.register()
    new = shop.signup("outra@exemplo.com")
    existing = shop.signup(EMAIL)
    n = len(shop.sent)

    assert (new.status_code, new.json()) == (existing.status_code, existing.json()) == (202, SENT)
    assert shop.signup(EMAIL).json() == SENT and len(shop.sent) == n  # conta verificada: nada é enviado
    assert shop.docs("shop_customers")[0]["email_verified"] is True


def test_signup_validation(shop):
    assert shop.signup(password="curta-11-ch").status_code == 422
    assert shop.signup(password="x" * 129).status_code == 422
    assert shop.signup(accept_terms=False).status_code == 422
    assert shop.signup(accept_adult=False).status_code == 422
    assert shop.signup(terms_version="0").status_code == 422
    assert shop.signup(role="admin").status_code == 422  # extra=forbid
    assert shop.signup("nao-e-email").status_code == 422
    assert shop.docs("shop_customers") == [] and shop.sent == []


def test_unverified_account_cannot_login_and_otp_hashed(shop):
    shop.signup()
    assert shop.login().status_code == 401
    (otp,) = [d for d in shop.docs("shop_otp") if d["purpose"] == "signup"]
    assert shop.last_code() not in otp["code_hash"] and len(otp["code_hash"]) == 64


def test_otp_5_wrong_invalidates(shop):
    shop.signup()
    good = shop.last_code()
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(5):
        res = shop.verify(wrong)
        assert (res.status_code, res.json()) == (400, BAD_OTP)
    res = shop.verify(good)  # o código certo também cai, com a MESMA mensagem
    assert (res.status_code, res.json()) == (400, BAD_OTP)


def test_otp_reuse_rejected(shop):
    shop.signup()
    code = shop.last_code()
    assert shop.verify(code).status_code == 200
    assert shop.verify(code).json() == BAD_OTP


def test_otp_expired_rejected(shop):
    shop.signup()
    shop.db.run(
        shop.db.db["shop_otp"].update_many({"purpose": "signup"}, {"$set": {"expires_at": now().replace(year=2020)}})
    )
    assert shop.verify().json() == BAD_OTP


def test_new_otp_invalidates_previous(shop):
    shop.signup()
    first = shop.last_code()
    shop.c.post(f"{S}/resend-otp", json={"email": EMAIL, "purpose": "signup"})
    second = shop.last_code()
    assert first != second  # 1 em 1.000.000 de colidir
    assert shop.verify(first).json() == BAD_OTP
    assert shop.verify(second).status_code == 200


def test_send_limit_4th_in_hour_is_429(shop, monkeypatch):
    monkeypatch.setattr(settings, "OTP_MAX_SENDS_PER_HOUR", 3)
    assert shop.signup().status_code == 202
    for _ in range(2):
        assert shop.c.post(f"{S}/resend-otp", json={"email": EMAIL, "purpose": "signup"}).status_code == 202
    res = shop.c.post(f"{S}/resend-otp", json={"email": EMAIL, "purpose": "signup"})
    assert res.status_code == 429 and res.json() == {"detail": "Aguarde para pedir um novo código."}
    assert len(shop.sent) == 3
    assert shop.verify().status_code == 200  # verificar nunca dá 429


def test_resend_cooldown(shop, monkeypatch):
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_S", 60)
    assert shop.signup().status_code == 202
    assert shop.c.post(f"{S}/resend-otp", json={"email": EMAIL, "purpose": "signup"}).status_code == 429


def test_send_limit_is_per_ip_too(shop, monkeypatch):
    monkeypatch.setattr(settings, "OTP_MAX_SENDS_PER_HOUR", 1)  # IP: 1 x 5 = 5 por hora
    codes = [shop.signup(f"u{i}@exemplo.com").status_code for i in range(7)]
    assert codes == [202] * 5 + [429] * 2


def test_resend_login_needs_prior_password_step(shop):
    shop.register()
    n = len(shop.sent)
    res = shop.c.post(f"{S}/resend-otp", json={"email": EMAIL, "purpose": "login"})
    assert (res.status_code, res.json()) == (202, SENT) and len(shop.sent) == n
    shop.login()
    shop.c.post(f"{S}/resend-otp", json={"email": EMAIL, "purpose": "login"})
    assert len(shop.sent) == n + 2


def test_login_same_401_for_unknown_wrong_unverified(shop):
    shop.register()
    shop.signup("pendente@exemplo.com")
    results = [
        shop.login("naoexiste@exemplo.com"),
        shop.login(EMAIL, "senha-errada-123"),
        shop.login("pendente@exemplo.com"),
    ]
    assert {(r.status_code, r.text) for r in results} == {(401, '{"detail":"E-mail ou senha incorretos."}')}


def test_login_brute_force_429(shop):
    shop.register()
    codes = [shop.login(EMAIL, "senha-errada-123").status_code for _ in range(settings.LOGIN_MAX_FAILURES + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {401}


def test_login_otp_wrong_5x_then_good_rejected(shop):
    shop.register()
    shop.login()
    good = shop.last_code("login")
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert shop.login_verify(wrong).status_code == 400
    assert shop.login_verify(good).json() == BAD_OTP


def test_signup_otp_not_valid_for_login(shop):
    shop.signup()
    code = shop.last_code()
    assert shop.login_verify(code).json() == BAD_OTP


def test_tokens_do_not_cross_audiences(shop):
    token = shop.register()["access_token"]
    for url in ("/api/v1/admin/overview", "/api/v1/auth/me"):
        assert shop.c.get(url, headers=shop.h(token)).status_code == 401
    assert shop.c.post("/api/v1/chat/questions", json={"question": "oi"}, headers=shop.h(token)).status_code == 401

    admin_h, admin = shop.db.create_admin()
    for tok in (admin_h["Authorization"].split()[1], create_access_token(admin["_id"], "admin", aud=AUD_ADMIN)):
        assert shop.c.get(f"{S}/me", headers=shop.h(tok)).status_code == 401
    cust = shop.docs("shop_customers")[0]["_id"]
    assert (
        shop.c.get(f"{S}/me", headers=shop.h(create_access_token(cust, "customer", aud=AUD_ADMIN))).status_code == 401
    )
    assert shop.c.get(f"{S}/me").status_code == 401


def test_logout_revokes(shop):
    token = shop.register()["access_token"]
    assert shop.c.post(f"{S}/logout", headers=shop.h(token)).status_code == 204
    assert shop.c.get(f"{S}/me", headers=shop.h(token)).status_code == 401
    assert shop.c.post(f"{S}/logout", headers=shop.h(token)).status_code == 401
    shop.login()
    assert shop.c.get(f"{S}/me", headers=shop.h(shop.login_verify().json()["access_token"])).status_code == 200


def test_deleted_or_forged_tv_is_401(shop):
    token = shop.register()["access_token"]
    cust = shop.docs("shop_customers")[0]
    forged = create_access_token(cust["_id"], "customer", aud=AUD_SHOP, token_version=7)
    assert shop.c.get(f"{S}/me", headers=shop.h(forged)).status_code == 401
    shop.db.run(shop.db.db["shop_customers"].update_one({"_id": cust["_id"]}, {"$set": {"deleted_at": now()}}))
    assert shop.c.get(f"{S}/me", headers=shop.h(token)).status_code == 401


def test_audit_has_events_and_no_pii(shop):
    token = shop.register()["access_token"]
    shop.login(EMAIL, "senha-errada-123")
    shop.login()
    shop.login_verify()
    shop.c.post(f"{S}/logout", headers=shop.h(token))
    audit = shop.docs("shop_audit")

    assert {"signup", "login_ok", "login_fail", "otp_sent", "logout"} <= {a["event"] for a in audit}
    blob = str(audit).lower()
    cust = shop.docs("shop_customers")[0]
    for secret in (EMAIL, "ana", cust["_id"], "testclient", PW, shop.last_code()):
        assert secret.lower() not in blob, secret


def test_otp_counters_are_persisted_and_pseudonymous(shop):
    shop.signup()
    kinds = {d["purpose"]: d for d in shop.docs("shop_otp")}

    assert {"signup", "rate_email", "rate_ip"} <= kinds.keys()
    assert kinds["rate_email"]["sends"] == 1 and kinds["rate_ip"]["sends"] == 1
    assert EMAIL not in kinds["rate_email"]["email"] and "testclient" not in kinds["rate_ip"]["email"]
    assert (kinds["rate_email"]["expires_at"] - kinds["rate_email"]["created_at"]).total_seconds() >= 3600


def test_mail_console_refused_in_prod(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_BACKEND", "console")
    monkeypatch.setattr(settings, "ENV", "prod")
    with pytest.raises(RuntimeError):
        mail.send_otp(EMAIL, "123456", "login")


def test_mail_smtp_blocks_crlf_before_connecting(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_BACKEND", "smtp")

    def boom(*a, **k):
        raise AssertionError("não deve abrir conexão")

    monkeypatch.setattr(mail.smtplib, "SMTP", boom)
    with pytest.raises(ValueError):
        mail.send_otp("a@exemplo.com\r\nBcc: x@y.com", "123456", "login")


def test_mail_smtp_body_has_only_code_and_minutes(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_BACKEND", "smtp")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.invalido")
    got = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            got["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context):
            got["tls"] = True

        def login(self, user, pwd):
            pass

        def send_message(self, msg):
            got["body"] = msg.get_content().strip()

    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSMTP)
    mail.send_otp("a@exemplo.com", "123456", "login")
    assert got == {"timeout": mail.SMTP_TIMEOUT_S, "tls": True, "body": "Seu código é 123456. Válido por 5 minutos."}
