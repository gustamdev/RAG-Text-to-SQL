from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.auth.security import decode_access_token
from app.config import settings
from app.core.errors import Forbidden, ServiceUnavailable, TooManyRequests, Unauthorized
from app.core.rate_limit import FailureLimiter, SlidingWindowLimiter
from app.database.connection import get_database
from app.database.repos.users import UserRepo
from app.database.sql_engine import SQLEngine
from app.schemas.common import Role
from app.services.agent_runner import AgentRunner
from app.services.product_analytics import ProductAnalytics
from app.services.query_runner import QueryRunner

_bearer = HTTPBearer(auto_error=False)


def get_db() -> AsyncDatabase:
    return get_database()


def get_query_runner(request: Request) -> QueryRunner:
    return request.app.state.query_runner


def get_agent_runner(request: Request) -> AgentRunner:
    return request.app.state.agent_runner


def get_sql_engine(request: Request) -> SQLEngine:
    """Motor DuckDB do snapshot. Sem snapshot (ou com arquivo corrompido) as rotas de dados dão 503."""
    runner = getattr(request.app.state, "query_runner", None)
    engine = getattr(runner, "engine", None)
    if engine is None or not engine.available:
        raise ServiceUnavailable("Base de produtos indisponível no momento.")
    return engine


def get_product_analytics(engine: SQLEngine = Depends(get_sql_engine)) -> ProductAnalytics:
    return ProductAnalytics(engine)


# --- Autenticação (admin) ------------------------------------------------------------------


def get_app_db() -> AsyncDatabase:
    """Banco das contas de admin (`MONGO_DB_NAME`, coleção `users`).

    Dependência separada de `get_db` só para os testes poderem trocar o banco de autenticação.
    """
    return get_database()


@dataclass
class Repos:
    users: UserRepo


def get_repos(db: AsyncDatabase = Depends(get_app_db)) -> Repos:
    return Repos(users=UserRepo(db))


def get_login_limiter(request: Request) -> FailureLimiter:
    limiter = getattr(request.app.state, "login_limiter", None)
    if limiter is None:
        limiter = FailureLimiter(settings.LOGIN_MAX_FAILURES, settings.LOGIN_WINDOW_S)
        request.app.state.login_limiter = limiter
    return limiter


def enforce_public_rate_limit(request: Request) -> None:
    """Limite por IP nas rotas públicas: elas recalculam agregações e dividem o motor SQL com o assistente."""
    limiter = getattr(request.app.state, "public_limiter", None)
    if limiter is None:
        limiter = SlidingWindowLimiter(settings.PUBLIC_RATE_LIMIT, settings.PUBLIC_RATE_WINDOW_S)
        request.app.state.public_limiter = limiter
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(ip):
        raise TooManyRequests("Muitas requisições. Aguarde um instante e tente de novo.")


def get_chat_limiter(request: Request) -> SlidingWindowLimiter:
    limiter = getattr(request.app.state, "chat_limiter", None)
    if limiter is None:
        limiter = SlidingWindowLimiter(settings.CHAT_RATE_LIMIT, settings.CHAT_RATE_WINDOW_S)
        request.app.state.chat_limiter = limiter
    return limiter


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    repos: Repos = Depends(get_repos),
) -> dict | None:
    """Usuário do token, se houver e for válido. O papel vem do banco, não do token."""
    if credentials is None:
        return None
    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise Unauthorized("Sessão inválida ou expirada. Entre novamente.")
    user = await repos.users.get(claims["sub"])
    if user is None:
        raise Unauthorized("Sessão inválida ou expirada. Entre novamente.")
    return user


async def get_current_user(user: dict | None = Depends(get_optional_user)) -> dict:
    if user is None:
        raise Unauthorized("Entre na sua conta para continuar.")
    return user


def require_roles(*roles: Role) -> Callable[..., dict]:
    allowed = {r.value for r in roles}

    async def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in allowed:
            raise Forbidden("Você não tem permissão para esta ação.")
        return user

    return dependency


require_admin = require_roles(Role.ADMIN)
