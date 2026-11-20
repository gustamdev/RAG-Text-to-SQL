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
            "terms_version": "2",
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


# ---- esqueci minha senha ----
NEW_PW = "outra-senha-longa-2"
FORGOT = {"masked_email": "a***@exemplo.com", "message": "Se o e-mail existir, enviamos um código."}
BAD_RESET = {"detail": "Código inválido ou expirado."}


def _forgot(shop, email=EMAIL):
    return shop.c.post(f"{S}/forgot-password", json={"email": email})


def _reset(shop, code=None, email=EMAIL, pw=NEW_PW):
    code = code or shop.last_code("reset")
    return shop.c.post(f"{S}/reset-password", json={"email": email, "code": code, "new_password": pw})


def _wrong(code):
    return "000000" if code != "000000" else "111111"


@pytest.fixture
def notices(monkeypatch):
    out: list[str] = []
    monkeypatch.setattr(mail, "send_password_changed", out.append)
    return out


def test_reset_happy_path_revokes_sessions(shop, notices):
    old = shop.register()["access_token"]
    res = _forgot(shop)
    assert (res.status_code, res.json()) == (202, FORGOT)
    code = shop.last_code("reset")
    assert shop.login().status_code == 202  # OTP de login pendente
    assert _reset(shop, code).json() == {"ok": True}
    assert shop.c.get(f"{S}/me", headers=shop.h(old)).status_code == 401
    assert shop.login(password=PW).status_code == 401
    assert shop.login(password=NEW_PW).status_code == 202
    assert shop.login_verify().status_code == 200
    assert notices == [EMAIL]
    assert not [d for d in shop.docs("shop_otp") if d.get("purpose") == "reset"]
    audit = str(shop.docs("shop_audit"))
    assert "password_reset" in audit and NEW_PW not in audit and code not in audit


def test_reset_clears_pending_login_otp(shop, notices):
    shop.register()
    shop.login()
    login_code = shop.last_code("login")
    _forgot(shop)
    assert _reset(shop).status_code == 200
    assert shop.login_verify(login_code).json() == BAD_OTP


def test_forgot_same_answer_for_unknown_unverified_deleted(shop):
    shop.signup("pend@exemplo.com")  # não verificada
    shop.sent.clear()
    shop.register()
    shop.sent.clear()
    shop.db.run(shop.db.db["shop_customers"].update_one({"email": EMAIL}, {"$set": {"deleted_at": now()}}))
    bodies = [_forgot(shop, e) for e in ("ghost@exemplo.com", "pend@exemplo.com", EMAIL)]
    assert {(r.status_code, r.text.replace("g***", "x").replace("p***", "x").replace("a***", "x")) for r in bodies} == {
        (202, bodies[0].text.replace("g***", "x"))
    }
    assert shop.sent == []


def test_forgot_existing_vs_unknown_identical_shape(shop):
    shop.register()
    shop.sent.clear()
    a, b = _forgot(shop), _forgot(shop, "ghost@exemplo.com")
    assert a.status_code == b.status_code == 202 and set(a.json()) == set(b.json())
    assert b.json()["message"] == a.json()["message"]
    assert [p for _, _, p in shop.sent] == ["reset"]


def test_reset_wrong_expired_reuse(shop, notices):
    shop.register()
    _forgot(shop)
    good = shop.last_code("reset")
    assert (_reset(shop, _wrong(good)).status_code, _reset(shop, _wrong(good)).json()) == (400, BAD_RESET)
    shop.db.run(
        shop.db.db["shop_otp"].update_many({"purpose": "reset"}, {"$set": {"expires_at": now().replace(year=2020)}})
    )
    assert _reset(shop, good).json() == BAD_RESET
    _forgot(shop)
    good = shop.last_code("reset")
    assert _reset(shop, good).status_code == 200
    assert _reset(shop, good).json() == BAD_RESET


def test_reset_max_attempts_invalidate(shop, notices):
    shop.register()
    _forgot(shop)
    good = shop.last_code("reset")
    for _ in range(5):
        assert _reset(shop, _wrong(good)).json() == BAD_RESET
    assert _reset(shop, good).json() == BAD_RESET
    assert shop.login(password=PW).status_code == 202 and notices == []


def test_reset_short_password_422_keeps_code(shop, notices):
    shop.register()
    _forgot(shop)
    assert _reset(shop, pw="curta-11-ch").status_code == 422
    assert _reset(shop).status_code == 200


def test_reset_unknown_unverified_deleted_is_generic_400(shop, notices):
    assert _reset(shop, "123456", "ghost@exemplo.com").json() == BAD_RESET
    shop.signup("pend@exemplo.com")
    assert _reset(shop, shop.last_code("signup"), "pend@exemplo.com").json() == BAD_RESET  # OTP de outro purpose
    shop.register()
    _forgot(shop)
    shop.db.run(shop.db.db["shop_customers"].update_one({"email": EMAIL}, {"$set": {"deleted_at": now()}}))
    assert _reset(shop).json() == BAD_RESET and notices == []


def test_signup_otp_not_valid_for_reset(shop):
    shop.signup()
    assert _reset(shop, shop.last_code("signup")).json() == BAD_RESET


def test_forgot_send_limit_429_for_any_email(shop, monkeypatch):
    monkeypatch.setattr(settings, "OTP_MAX_SENDS_PER_HOUR", 2)
    shop.register()
    codes = [_forgot(shop).status_code for _ in range(3)]
    assert codes == [202, 202, 429]
    assert _forgot(shop, "ghost@exemplo.com").status_code == 202  # outro e-mail: balde próprio
    shop.login()  # envio de login não foi esgotado pelo reset
    assert shop.login_verify().status_code == 200


def test_forgot_cooldown_429(shop, monkeypatch):
    monkeypatch.setattr(settings, "OTP_RESEND_COOLDOWN_S", 60)
    assert _forgot(shop).status_code == 202 and _forgot(shop).status_code == 429


def test_reset_clears_own_login_counter_only(shop, notices):
    shop.register()
    for _ in range(2):
        shop.login(password="senha-errada-123")
    _forgot(shop)
    _reset(shop)
    kinds = {d["purpose"] for d in shop.docs("shop_otp")}
    assert "rate_login_email" not in kinds and {"rate_login_ip", "rate_login_pair"} <= kinds


def test_mail_reset_texts(monkeypatch, caplog):
    monkeypatch.setattr(settings, "MAIL_BACKEND", "console")
    with caplog.at_level("INFO"):
        mail.send_otp("ana@exemplo.com", "123456", "reset")
        mail.send_password_changed("ana@exemplo.com")
    assert "redefinir senha" in caplog.text and "senha alterada" in caplog.text and "ana@" not in caplog.text


# --- troca de senha autenticada (PATCH /shop/account/password) ---

PWD = "/api/v1/shop/account/password"


def _change(shop, token, current=PW, new="outra-senha-longa-2", **over):
    body = {"current_password": current, "new_password": new, **over}
    return shop.c.patch(PWD, json=body, headers=shop.h(token))


@pytest.fixture
def pw(shop, monkeypatch):
    notes: list[str] = []
    monkeypatch.setattr(mail, "send_password_changed", notes.append)
    return shop, shop.register()["access_token"], notes


def test_change_password_ok_revokes_sessions_and_notifies(pw):
    shop, token, notes = pw
    res = _change(shop, token, code="123456")  # `code` legado é aceito e descartado
    assert res.status_code == 204 and notes == [EMAIL]
    assert shop.c.get(f"{S}/me", headers=shop.h(token)).status_code == 401  # sessão antiga revogada
    assert shop.login(password=PW).status_code == 401
    assert shop.login(password="outra-senha-longa-2").status_code == 202
    assert any(a["event"] == "password_changed" for a in shop.docs("shop_audit"))


def test_change_password_wrong_current(pw):
    shop, token, notes = pw
    res = _change(shop, token, current="errada-errada-1")
    assert res.status_code == 401 and res.json() == {"detail": "Senha atual incorreta."} and notes == []
    assert shop.c.get(f"{S}/me", headers=shop.h(token)).status_code == 200


def test_change_password_same_or_short_is_422(pw):
    shop, token, _ = pw
    assert _change(shop, token, new=PW).status_code == 422
    assert _change(shop, token, new="curta-11-ch").status_code == 422
    assert _change(shop, token, new="x" * 129).status_code == 422


def test_change_password_requires_token(pw):
    shop, _, _ = pw
    assert shop.c.patch(PWD, json={"current_password": PW, "new_password": "outra-senha-longa-2"}).status_code == 401


def test_change_password_rate_limit_after_5_failures(pw):
    shop, token, _ = pw
    assert [_change(shop, token, current="errada-errada-1").status_code for _ in range(5)] == [401] * 5
    assert _change(shop, token).status_code == 429  # com a senha certa também
