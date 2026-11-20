"""Backoffice da loja (só admin): clientes e pedidos com dados pessoais mascarados."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_app_db, require_admin
from app.config import settings
from app.core.errors import TooManyRequests
from app.core.rate_limit import SlidingWindowLimiter
from app.schemas.shop_account import AdminCustomerRow, AdminOrderRow, AdminPage
from app.services.shop_admin import ShopAdmin

router = APIRouter(prefix="/admin/shop", tags=["backoffice-shop"])

Page = Annotated[int, Query(ge=1, le=100_000)]
Size = Annotated[int, Query(ge=1, le=100)]
Purpose = Annotated[Literal["suporte", "auditoria", "analise"], Query(description="Finalidade do acesso (auditada)")]


def get_shop_admin(db: AsyncDatabase = Depends(get_app_db)) -> ShopAdmin:
    return ShopAdmin(db)


def admin_guard(request: Request, admin: dict = Depends(require_admin)) -> dict:
    """Limite por admin (janela deslizante, em memória): contém varredura em massa de dados de clientes."""
    limiter = getattr(request.app.state, "admin_shop_limiter", None)
    if limiter is None:
        limiter = request.app.state.admin_shop_limiter = SlidingWindowLimiter(
            settings.ADMIN_SHOP_RATE_LIMIT, settings.ADMIN_SHOP_RATE_WINDOW_S
        )
    if not limiter.allow(admin["_id"]):
        raise TooManyRequests("Muitas consultas. Aguarde um pouco e tente de novo.")
    return admin


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/customers", response_model=AdminPage[AdminCustomerRow])
async def customers(
    request: Request,
    page: Page = 1,
    page_size: Size = 20,
    purpose: Purpose = "suporte",
    admin: dict = Depends(admin_guard),
    svc: ShopAdmin = Depends(get_shop_admin),
) -> AdminPage[AdminCustomerRow]:
    return await svc.customer_page(admin["_id"], _ip(request), page, page_size, purpose)


@router.get("/orders", response_model=AdminPage[AdminOrderRow])
async def orders(
    request: Request,
    page: Page = 1,
    page_size: Size = 20,
    purpose: Purpose = "suporte",
    admin: dict = Depends(admin_guard),
    svc: ShopAdmin = Depends(get_shop_admin),
) -> AdminPage[AdminOrderRow]:
    return await svc.order_page(admin["_id"], _ip(request), page, page_size, purpose)
