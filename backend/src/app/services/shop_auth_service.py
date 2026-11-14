"""Identidade do cliente da loja: cadastro e login com MFA por e-mail (OTP).

Sem enumeração de contas: cadastro responde igual para e-mail novo/existente, login responde igual
para conta inexistente/senha errada/não verificada, e o OTP inválido nunca revela bloqueio.
"""

import asyncio
import hashlib
import hmac
import logging
import secrets
import uuid
import weakref
from collections.abc import Callable

from pymongo.asynchronous.database import AsyncDatabase

from app.auth.security import AUD_SHOP, create_access_token, hash_password, verify_password
from app.config import settings
from app.core.errors import BadRequest, TooManyRequests, Unauthorized
from app.core.rate_limit import FailureLimiter
from app.core.timeutil import iso, now
from app.database.repos.shop_audit import ShopAuditRepo
from app.database.repos.shop_customers import ShopCustomerRepo
from app.database.repos.shop_otp import ShopOtpRepo
from app.database.repos.users import EmailTaken
from app.schemas.common import Role
from app.schemas.shop_auth import (
    CustomerOut,
    MfaRequiredOut,
    ResendOtpRequest,
    ShopLoginRequest,
    ShopTokenResponse,
    SignupRequest,
    VerifyOtpRequest,
)
from app.services import mail

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "E-mail ou senha incorretos."
INVALID_OTP = "Código inválido ou expirado"
SEND_LIMIT = "Aguarde para pedir um novo código."
CODE_SENT = "Se o e-mail puder ser usado, enviamos um código."
ARGON_CONCURRENCY = 2
IP_SENDS_FACTOR = 5  # limite de envios por IP/h = fator x limite por e-mail

_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


async def _argon(fn: Callable, *args):
    """argon2 (~64 MiB, CPU) fora do event loop e com concorrência limitada: login em massa não esgota a RAM."""
    loop = asyncio.get_running_loop()
    sem = _semaphores.setdefault(loop, asyncio.Semaphore(ARGON_CONCURRENCY))
    async with sem:
        return await asyncio.to_thread(fn, *args)


def pseudo(value: str) -> str:
    """Pseudônimo estável (HMAC) para auditoria e contadores: nunca grava e-mail, IP ou id em claro."""
    return hmac.new(settings.PSEUDONYM_KEY.get_secret_value().encode(), value.encode(), hashlib.sha256).hexdigest()[:32]


def otp_hash(email: str, purpose: str, code: str) -> str:
    key = settings.OTP_PEPPER.get_secret_value().encode()
    return hmac.new(key, f"{purpose}:{email}:{code}".encode(), hashlib.sha256).hexdigest()


def customer_out(c: dict) -> CustomerOut:
    return CustomerOut(
        id=c["_id"],
        nickname=c.get("nickname"),
        email=c["email"],
        terms_version=c["terms_version"],
        created_at=iso(c["created_at"]),
    )


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _active(c: dict | None) -> bool:
    return c is not None and bool(c.get("email_verified")) and not c.get("deleted_at")


async def _deliver(email: str, code: str, purpose: str) -> None:
    try:
        await asyncio.to_thread(mail.send_otp, email, code, purpose)
    except Exception:  # noqa: BLE001 - envio roda em segundo plano; o log não leva e-mail nem código
        logger.exception("Falha ao enviar OTP (%s).", purpose)


class ShopAuthService:
    def __init__(self, db: AsyncDatabase, limiter: FailureLimiter):
        self.customers = ShopCustomerRepo(db)
        self.otp = ShopOtpRepo(db)
        self.audit = ShopAuditRepo(db)
        self.limiter = limiter

    async def _audit(self, event: str, source: str, ip: str) -> None:
        try:
            await self.audit.add(event, pseudo(source), pseudo(f"ip:{ip}"))
        except Exception:  # noqa: BLE001 - auditoria não derruba o login
            logger.exception("Falha ao gravar auditoria (%s).", event)

    async def _reserve_send(self, email: str, ip: str) -> None:
        """Limites de envio persistidos (IP, e-mail, cooldown). Conta SEMPRE, exista a conta ou não."""
        per_email = settings.OTP_MAX_SENDS_PER_HOUR
        if not await self.otp.allow_send(pseudo(f"ip:{ip}"), "rate_ip", per_email * IP_SENDS_FACTOR, 0) or not (
            await self.otp.allow_send(pseudo(f"email:{email}"), "rate_email", per_email, settings.OTP_RESEND_COOLDOWN_S)
        ):
            raise TooManyRequests(SEND_LIMIT)

    async def _send_code(self, email: str, purpose: str, ip: str, spawn: Callable, source: str) -> None:
        code = f"{secrets.randbelow(10**6):06d}"
        await self.otp.issue(email, purpose, otp_hash(email, purpose, code), settings.OTP_TTL_S)
        spawn(_deliver, email, code, purpose)
        await self._audit("otp_sent", source, ip)

    async def _consume(self, email: str, purpose: str, code: str) -> None:
        if not await self.otp.consume(email, purpose, otp_hash(email, purpose, code), settings.OTP_MAX_ATTEMPTS):
            raise BadRequest(INVALID_OTP)

    @staticmethod
    def _token(customer: dict) -> ShopTokenResponse:
        token = create_access_token(
            customer["_id"], Role.CUSTOMER.value, aud=AUD_SHOP, token_version=customer.get("token_version", 0)
        )
        return ShopTokenResponse(access_token=token, customer=customer_out(customer))

    async def signup(self, p: SignupRequest, ip: str, spawn: Callable) -> str:
        email = p.email.strip().lower()
        await self._reserve_send(email, ip)
        t = now()
        # O argon2 roda sempre (também para e-mail existente): o tempo não entrega se a conta existe.
        password_hash = await _argon(hash_password, p.password)
        fields = {
            "nickname": p.nickname,
            "password_hash": password_hash,
            "terms_version": p.terms_version,
            "terms_accepted_at": t,
            "adult_confirmed": True,
        }
        existing = await self.customers.get_by_email(email)
        customer_id = None
        if existing is None:
            doc = {
                "_id": uuid.uuid4().hex,
                "email": email,
                **fields,
                "email_verified": False,
                "token_version": 0,
                "created_at": t,
                "last_login_at": None,
                "deleted_at": None,
            }
            try:
                customer_id = (await self.customers.create(doc))["_id"]
            except EmailTaken:
                pass
        elif not existing.get("email_verified") and not existing.get("deleted_at"):
            # shortcut: o último cadastro pendente vence (pré-sequestro limitado ao TTL do OTP).
            await self.customers.update_pending(email, fields)
            customer_id = existing["_id"]
        if customer_id:
            await self._audit("signup", customer_id, ip)
            await self._send_code(email, "signup", ip, spawn, customer_id)
        return CODE_SENT

    async def verify_signup(self, p: VerifyOtpRequest, ip: str) -> ShopTokenResponse:
        email = p.email.strip().lower()
        await self._consume(email, "signup", p.code)
        customer = await self.customers.get_by_email(email)
        if customer is None or customer.get("deleted_at"):
            raise BadRequest(INVALID_OTP)
        await self.customers.mark_verified(customer["_id"])
        return self._token({**customer, "email_verified": True})

    async def resend(self, p: ResendOtpRequest, ip: str, spawn: Callable) -> str:
        email = p.email.strip().lower()
        await self._reserve_send(email, ip)
        customer = await self.customers.get_by_email(email)
        if p.purpose == "signup":
            can = customer is not None and not customer.get("email_verified") and not customer.get("deleted_at")
        else:  # só reenvia login se a senha já foi aceita (há OTP de login emitido): reenvio não é porta lateral
            can = _active(customer) and await self.otp.has(email, "login")
        if can:
            await self._send_code(email, p.purpose, ip, spawn, customer["_id"])
        return CODE_SENT

    async def login(self, p: ShopLoginRequest, ip: str, spawn: Callable) -> MfaRequiredOut:
        email = p.email.strip().lower()
        key, email_key = f"shop:{email}|{ip}", f"shop-email:{email}"
        if self.limiter.is_blocked(key):
            await self._audit("login_fail", email, ip)
            raise TooManyRequests("Muitas tentativas. Aguarde alguns minutos e tente de novo.")
        # Atraso progressivo por e-mail, contado ANTES de dormir (rajadas paralelas também pagam), como no admin.
        attempts = self.limiter.count(email_key)
        self.limiter.register_failure(email_key)
        self.limiter.register_failure(key)
        extra = attempts - settings.LOGIN_FREE_ATTEMPTS_PER_EMAIL
        if extra >= 0:
            await asyncio.sleep(min(2 ** min(extra, 10), settings.LOGIN_MAX_DELAY_S))
        customer = await self.customers.get_by_email(email)
        ok = await _argon(verify_password, p.password, customer["password_hash"] if customer else None)
        if not ok or not _active(customer):
            await self._audit("login_fail", email, ip)
            raise Unauthorized(INVALID_CREDENTIALS)
        self.limiter.reset(key)
        self.limiter.reset(email_key)
        await self._reserve_send(email, ip)
        await self._send_code(email, "login", ip, spawn, customer["_id"])
        return MfaRequiredOut(masked_email=_mask_email(email))

    async def verify_login(self, p: VerifyOtpRequest, ip: str) -> ShopTokenResponse:
        email = p.email.strip().lower()
        await self._consume(email, "login", p.code)
        customer = await self.customers.get_by_email(email)
        if not _active(customer):
            raise BadRequest(INVALID_OTP)
        await self.customers.touch_login(customer["_id"])
        await self._audit("login_ok", customer["_id"], ip)
        return self._token(customer)

    async def logout(self, customer: dict, ip: str) -> None:
        await self.customers.bump_token_version(customer["_id"])
        await self._audit("logout", customer["_id"], ip)
