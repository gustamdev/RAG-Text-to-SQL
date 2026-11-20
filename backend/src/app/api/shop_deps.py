"""Dependências da loja: cliente autenticado (aud=shop) e serviço de identidade."""

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import enforce_customer_rate_limit, get_app_db
from app.auth.security import AUD_SHOP, decode_access_token
from app.core.errors import Unauthorized
from app.database.repos.shop_customers import ShopCustomerRepo
from app.services.shop_auth_service import ShopAuthService

_bearer = HTTPBearer(auto_error=False)
_INVALID = "Sessão inválida ou expirada. Entre novamente."


class SnapshotRefresher:
    """Contrato `await refresher.request()`. Esta classe é o no-op (app sem snapshot, testes);
    a implementação real é `services.snapshot.SnapshotService`, em `app.state.snapshot_service`."""

    async def request(self) -> None:
        return None


def get_snapshot_refresher(request: Request) -> SnapshotRefresher:
    return getattr(request.app.state, "snapshot_service", None) or SnapshotRefresher()


def get_shop_auth_service(db: AsyncDatabase = Depends(get_app_db)) -> ShopAuthService:
    return ShopAuthService(db)


async def get_current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncDatabase = Depends(get_app_db),
) -> dict:
    """Cliente autenticado (documento de shop_customers). Testes das outras rotas a sobrescrevem."""
    if credentials is None:
        raise Unauthorized("Entre na sua conta para continuar.")
    claims = decode_access_token(credentials.credentials, AUD_SHOP)
    if claims is None:
        raise Unauthorized(_INVALID)
    customer = await ShopCustomerRepo(db).get(claims["sub"])
    # tv ausente/diferente = revogado (logout/exclusão); conta não verificada ou apagada também é 401.
    if (
        customer is None
        or claims.get("tv") != customer.get("token_version", 0)
        or not customer.get("email_verified")
        or customer.get("deleted_at")
    ):
        raise Unauthorized(_INVALID)
    return customer


async def get_limited_customer(request: Request, customer: dict = Depends(get_current_customer)) -> dict:
    """Cliente autenticado + limite por customer_id. Use em todas as rotas autenticadas da loja (inclusive checkout)."""
    enforce_customer_rate_limit(request, customer["_id"])
    return customer
