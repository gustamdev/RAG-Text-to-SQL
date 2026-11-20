"""Identidade do cliente da loja: cadastro e login com MFA por e-mail (OTP).

Sem enumeração de contas: cadastro responde igual para e-mail novo/existente, login responde igual
para conta inexistente/senha errada/não verificada, e o OTP inválido nunca revela bloqueio.
"""

import asyncio
import hashlib
import hmac
import ipaddress
import logging
import secrets
import uuid
import weakref
from collections.abc import Callable
from datetime import timedelta

from pymongo.asynchronous.database import AsyncDatabase

from app.auth.security import AUD_SHOP, create_access_token, hash_password, verify_password
from app.config import settings
from app.core.errors import BadRequest, TooManyRequests, Unauthorized
from app.core.timeutil import iso, now
from app.database.repos.shop_audit import ShopAuditRepo
from app.database.repos.shop_customers import ShopCustomerRepo
from app.database.repos.shop_otp import ShopOtpRepo
from app.database.repos.users import EmailTaken
from app.schemas.common import Role
from app.schemas.shop_auth import (
    CustomerOut,
    ForgotPasswordRequest,
    MfaRequiredOut,
    ResendOtpRequest,
    ResetPasswordRequest,
    ShopLoginRequest,
    ShopTokenResponse,
    SignupRequest,
    VerifyOtpRequest,
)
from app.services import mail

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "E-mail ou senha incorretos."
INVALID_OTP = "Código inválido ou expirado"
INVALID_RESET = "Código inválido ou expirado."
RESET_SENT = "Se o e-mail existir, enviamos um código."
SEND_LIMIT = "Aguarde para pedir um novo código."
CODE_SENT = "Se o e-mail puder ser usado, enviamos um código."
ARGON_CONCURRENCY = 2
IP_SENDS_FACTOR = 5  # limite de envios por IP/h = fator x limite por e-mail
OTP_TOTAL_ATTEMPTS_FACTOR = 4  # teto total de chutes = fator x teto por IP (um IP estranho não queima o OTP legítimo)
PENDING_TTL = timedelta(
    hours=settings.SHOP_UNVERIFIED_TTL_HOURS
)  # conta não verificada some depois disso (TTL em pending_expires_at)
_IP_EVENTS = frozenset({"login_fail", "otp_sent"})  # só eventos de risco guardam o pseudônimo do IP

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
        phone=c.get("phone"),
        terms_version=c["terms_version"],
        created_at=iso(c["created_at"]),
    )


def _ip_net(ip: str) -> str:
    """IPv4 truncado ao /24 (IPv6 ao /64) antes do HMAC: o pseudônimo identifica a rede, não a casa."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    return str(ipaddress.ip_network(f"{addr}/{24 if addr.version == 4 else 64}", strict=False))


def _active(c: dict | None) -> bool:
    return c is not None and bool(c.get("email_verified")) and not c.get("deleted_at")


async def _notify_password_changed(email: str) -> None:
    try:
        await asyncio.to_thread(mail.send_password_changed, email)
    except Exception as exc:  # noqa: BLE001 - só o tipo no log (a mensagem pode ter e-mail)
        logger.error("Falha ao enviar aviso de senha alterada: %s", type(exc).__name__)


async def _deliver(email: str, code: str, purpose: str) -> None:
    try:
        await asyncio.to_thread(mail.send_otp, email, code, purpose)
    except Exception as exc:  # noqa: BLE001 - segundo plano; só o tipo no log (a mensagem pode ter e-mail/código)
        logger.error("Falha ao enviar OTP (%s): %s", purpose, type(exc).__name__)


class ShopAuthService:
    def __init__(self, db: AsyncDatabase):
        self.customers = ShopCustomerRepo(db)
        self.otp = ShopOtpRepo(db)
        self.audit = ShopAuditRepo(db)

    async def _audit(self, event: str, source: str, ip: str | None = None, meta: dict | None = None) -> None:
        ip_hmac = pseudo(f"ip:{_ip_net(ip)}") if ip and event in _IP_EVENTS else None
        try:
            await self.audit.add(event, pseudo(source), ip_hmac, meta)
        except Exception:  # noqa: BLE001 - auditoria não derruba o login
            logger.exception("Falha ao gravar auditoria (%s).", event)

    @staticmethod
    def _buckets(login: bool, reset: bool = False) -> tuple[str, str]:
        # Envio de login/reset tem baldes PRÓPRIOS: cadastro/reenvio anônimos não esgotam o login do dono do e-mail.
        if reset:
            return "rate_rsend_email", "rate_rsend_ip"
        return ("rate_lsend_email", "rate_lsend_ip") if login else ("rate_email", "rate_ip")

    async def _can_send_login(self, email: str, ip: str) -> bool:
        b_email, b_ip = self._buckets(True)
        per_email = settings.OTP_MAX_SENDS_PER_HOUR
        return await self.otp.can_send(
            pseudo(f"email:{email}"), b_email, per_email, settings.OTP_RESEND_COOLDOWN_S
        ) and await self.otp.can_send(pseudo(f"ip:{ip}"), b_ip, per_email * IP_SENDS_FACTOR, 0)

    async def _reserve_send(self, email: str, ip: str, login: bool = False, reset: bool = False) -> None:
        """Limites de envio persistidos (IP, e-mail, cooldown). Conta SEMPRE, exista a conta ou não."""
        b_email, b_ip = self._buckets(login, reset)
        per_email = settings.OTP_MAX_SENDS_PER_HOUR
        if not await self.otp.allow_send(pseudo(f"ip:{ip}"), b_ip, per_email * IP_SENDS_FACTOR, 0) or not (
            await self.otp.allow_send(pseudo(f"email:{email}"), b_email, per_email, settings.OTP_RESEND_COOLDOWN_S)
        ):
            raise TooManyRequests(SEND_LIMIT)

    async def _send_code(self, email: str, purpose: str, ip: str, spawn: Callable, source: str) -> None:
        code = f"{secrets.randbelow(10**6):06d}"
        await self.otp.issue(email, purpose, otp_hash(email, purpose, code), settings.OTP_TTL_S)
        spawn(_deliver, email, code, purpose)
        await self._audit("otp_sent", source, ip)

    async def _consume(self, email: str, purpose: str, code: str, ip: str) -> None:
        per_ip = settings.OTP_MAX_ATTEMPTS
        total = per_ip * OTP_TOTAL_ATTEMPTS_FACTOR
        ok = await self.otp.consume(email, purpose, otp_hash(email, purpose, code), total, per_ip, pseudo(f"ip:{ip}"))
        if not ok:
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
            "pending_expires_at": t + PENDING_TTL,
            "nickname": p.nickname,
            "password_hash": password_hash,
            "terms_version": p.terms_version,
            "terms_accepted_at": t,
            "adult_confirmed": True,
        }
        existing = await self.customers.get_by_email(email)
        customer_id, applied = None, False
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
                applied = True
            except EmailTaken:
                pass
        elif not existing.get("email_verified") and not existing.get("deleted_at"):
            # Com OTP de signup vivo a senha pendente NÃO muda (só reenvia): senão um 2º cadastro sequestraria a conta.
            # Risco residual: depois do OTP expirar o último cadastro pendente vence; o login sempre exige OTP no
            # e-mail do dono, então quem cadastrou primeiro não entra sem acesso à caixa de entrada.
            if not await self.otp.has(email, "signup"):
                await self.customers.update_pending(email, fields)
                applied = True
            customer_id = existing["_id"]
        if customer_id:
            await self._audit("signup", customer_id)
            if applied:
                await self._audit("terms_accepted", customer_id, meta={"version": p.terms_version})
            await self._send_code(email, "signup", ip, spawn, customer_id)
        return CODE_SENT

    async def verify_signup(self, p: VerifyOtpRequest, ip: str) -> ShopTokenResponse:
        email = p.email.strip().lower()
        await self._consume(email, "signup", p.code, ip)
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
        # Contadores persistidos (HMAC; sem e-mail/IP em claro), contados ANTES de dormir: rajadas paralelas pagam.
        window = settings.LOGIN_WINDOW_S
        n_email, n_ip, n_pair = await asyncio.gather(
            self.otp.bump(pseudo(f"login-email:{email}"), "rate_login_email", window),
            self.otp.bump(pseudo(f"login-ip:{ip}"), "rate_login_ip", window),
            self.otp.bump(pseudo(f"login-pair:{email}|{ip}"), "rate_login_pair", window),
        )
        if n_pair > settings.LOGIN_MAX_FAILURES or n_ip > settings.LOGIN_MAX_FAILURES * IP_SENDS_FACTOR:
            await self._audit("login_fail", email, ip)
            raise TooManyRequests("Muitas tentativas. Aguarde alguns minutos e tente de novo.")
        extra = n_email - 1 - settings.LOGIN_FREE_ATTEMPTS_PER_EMAIL
        if extra >= 0:
            await asyncio.sleep(min(2 ** min(extra, 10), settings.LOGIN_MAX_DELAY_S))
        # 429 de envio ANTES de olhar a senha: a resposta não revela se a senha está certa.
        if not await self._can_send_login(email, ip):
            raise TooManyRequests(SEND_LIMIT)
        customer = await self.customers.get_by_email(email)
        ok = await _argon(verify_password, p.password, customer["password_hash"] if customer else None)
        if not ok or not _active(customer):
            await self._audit("login_fail", email, ip)
            raise Unauthorized(INVALID_CREDENTIALS)
        await self.otp.reset(pseudo(f"login-pair:{email}|{ip}"), "rate_login_pair")
        await self.otp.reset(pseudo(f"login-email:{email}"), "rate_login_email")
        try:
            await self._reserve_send(email, ip, login=True)
        except TooManyRequests:  # corrida entre a consulta e a reserva: não confirma a senha
            raise Unauthorized(INVALID_CREDENTIALS) from None
        await self._send_code(email, "login", ip, spawn, customer["_id"])
        return MfaRequiredOut(masked_email=mail.mask_email(email))

    async def verify_login(self, p: VerifyOtpRequest, ip: str) -> ShopTokenResponse:
        email = p.email.strip().lower()
        await self._consume(email, "login", p.code, ip)
        customer = await self.customers.get_by_email(email)
        if not _active(customer):
            raise BadRequest(INVALID_OTP)
        await self.customers.touch_login(customer["_id"])
        await self._audit("login_ok", customer["_id"])
        return self._token(customer)

    async def forgot_password(self, p: ForgotPasswordRequest, ip: str, spawn: Callable) -> dict:
        """Resposta idêntica exista a conta ou não; só conta verificada e não deletada recebe o código."""
        email = p.email.strip().lower()
        await self._reserve_send(email, ip, reset=True)  # conta SEMPRE: 429 não revela a conta
        customer = await self.customers.get_by_email(email)
        if _active(customer):
            await self._send_code(email, "reset", ip, spawn, customer["_id"])
        return {"masked_email": mail.mask_email(email), "message": RESET_SENT}

    async def reset_password(self, p: ResetPasswordRequest, ip: str, spawn: Callable) -> None:
        email = p.email.strip().lower()
        try:
            await self._consume(email, "reset", p.code, ip)
        except BadRequest:
            raise BadRequest(INVALID_RESET) from None
        customer = await self.customers.get_by_email(email)
        if not _active(customer):
            raise BadRequest(INVALID_RESET)
        password_hash = await _argon(hash_password, p.new_password)
        if not await self.customers.set_password(customer["_id"], password_hash):
            raise BadRequest(INVALID_RESET)
        # Invalida OTPs pendentes (login/reset) e limpa só o contador do PRÓPRIO e-mail (nunca o do IP/par).
        await self.otp.reset(email, "login")
        await self.otp.reset(email, "reset")
        await self.otp.reset(pseudo(f"login-email:{email}"), "rate_login_email")
        await self._audit("password_reset", customer["_id"])
        spawn(_notify_password_changed, email)

    async def logout(self, customer: dict) -> None:
        await self.customers.bump_token_version(customer["_id"])
        await self._audit("logout", customer["_id"])
