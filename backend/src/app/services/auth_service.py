import asyncio

from app.auth.security import create_access_token, verify_password
from app.config import settings
from app.core.errors import TooManyRequests, Unauthorized
from app.core.rate_limit import FailureLimiter
from app.database.repos.users import UserRepo
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.common import Role
from app.services.mappers import user_out

INVALID_CREDENTIALS = "E-mail ou senha incorretos."


def token_response(user: dict) -> TokenResponse:
    token = create_access_token(user["_id"], user["role"], token_version=user.get("token_version", 0))
    return TokenResponse(access_token=token, user=user_out(user))


async def login(users: UserRepo, limiter: FailureLimiter, payload: LoginRequest, client_ip: str) -> TokenResponse:
    """Login do backoffice: só administradores entram.

    Conta inexistente, senha errada e conta sem perfil admin dão a MESMA resposta e contam como
    falha no limitador, para a API não revelar se um e-mail existe nem qual é o papel dele.
    """
    email = payload.email.strip().lower()
    key = f"{email}|{client_ip}"
    if limiter.is_blocked(key):
        raise TooManyRequests("Muitas tentativas. Aguarde alguns minutos e tente de novo.")
    # Atraso progressivo por e-mail (vale com qualquer IP): nunca tranca a conta, só encarece o chute.
    # A tentativa é contada ANTES de dormir, então requisições paralelas também pagam atraso crescente.
    email_key = f"email:{email}"
    attempts = limiter.count(email_key)
    limiter.register_failure(email_key)
    # Falha provisória de e-mail|IP também ANTES do await: rajadas paralelas contam; sucesso faz reset.
    limiter.register_failure(key)
    extra = attempts - settings.LOGIN_FREE_ATTEMPTS_PER_EMAIL
    if extra >= 0:
        await asyncio.sleep(min(2 ** min(extra, 10), settings.LOGIN_MAX_DELAY_S))
    user = await users.get_by_email(email)
    # argon2 é CPU-bound (~64 MiB): fora do event loop, senão uma enxurrada de logins trava a API inteira.
    password_ok = await asyncio.to_thread(verify_password, payload.password, user["password_hash"] if user else None)
    if not password_ok or user is None or user.get("role") != Role.ADMIN.value:
        raise Unauthorized(INVALID_CREDENTIALS)
    limiter.reset(key)
    limiter.reset(email_key)
    return token_response(user)
