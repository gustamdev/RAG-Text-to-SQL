"""Checkout, pagamento simulado e pedidos do cliente (aud=shop). Estado, preço, frete e total nunca vêm do cliente."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import JSONResponse
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_app_db
from app.api.shop_deps import SnapshotRefresher, get_limited_customer, get_snapshot_refresher
from app.core.errors import TooManyRequests
from app.core.rate_limit import SlidingWindowLimiter
from app.schemas.shop_orders import CancelIn, CheckoutIn, OrderOut, OrdersPage, PayIn
from app.services.shop_checkout import InsufficientStock, ShopCheckout

# Sem prefixo: o checkout vive em /shop/checkout e os pedidos em /shop/orders.
router = APIRouter(tags=["shop-checkout"])

WRITE_LIMIT, WRITE_WINDOW_S = 20, 60.0  # escritas (checkout/pay/cancel) por cliente
IdemKey = Annotated[str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9_-]{8,64}$")]
OrderId = Annotated[str, Path(min_length=1, max_length=64)]


def _ip(request: Request) -> str:
    return request.client.host if request.client else ""


def enforce_write_limit(request: Request, customer: dict = Depends(get_limited_customer)) -> dict:
    """Limite por cliente nas escritas; devolve o cliente para a rota."""
    limiter = getattr(request.app.state, "shop_write_limiter", None)
    if limiter is None:
        limiter = request.app.state.shop_write_limiter = SlidingWindowLimiter(WRITE_LIMIT, WRITE_WINDOW_S)
    if not limiter.allow(customer["_id"]):
        raise TooManyRequests("Muitas requisições. Aguarde um instante e tente de novo.")
    return customer


def get_checkout(
    db: AsyncDatabase = Depends(get_app_db), refresher: SnapshotRefresher = Depends(get_snapshot_refresher)
) -> ShopCheckout:
    return ShopCheckout(db, refresher)


@router.post("/shop/checkout", response_model=OrderOut, status_code=201)
async def create_order(
    body: CheckoutIn,
    request: Request,
    key: IdemKey,
    customer: dict = Depends(enforce_write_limit),
    svc: ShopCheckout = Depends(get_checkout),
) -> JSONResponse:
    try:
        status, response = await svc.checkout(customer["_id"], key, body, _ip(request))
    except InsufficientStock as exc:
        return JSONResponse(status_code=409, content={"detail": exc.detail, "items": exc.items})
    return JSONResponse(status_code=status, content=response)


@router.post("/shop/checkout/{order_id}/pay")
async def pay_order(
    order_id: OrderId,
    body: PayIn,
    request: Request,
    key: IdemKey,
    customer: dict = Depends(enforce_write_limit),
    svc: ShopCheckout = Depends(get_checkout),
) -> JSONResponse:
    status, response = await svc.pay(customer["_id"], order_id, key, body, _ip(request))
    return JSONResponse(status_code=status, content=response)


@router.post("/shop/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: OrderId,
    request: Request,
    body: CancelIn | None = None,  # sem corpo = motivo "other"
    customer: dict = Depends(enforce_write_limit),
    svc: ShopCheckout = Depends(get_checkout),
) -> OrderOut:
    return await svc.cancel(customer["_id"], order_id, (body or CancelIn()).reason, _ip(request))


@router.get("/shop/orders", response_model=OrdersPage)
async def list_orders(
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    customer: dict = Depends(get_limited_customer),
    svc: ShopCheckout = Depends(get_checkout),
) -> OrdersPage:
    return await svc.list_orders(customer["_id"], page, page_size)


@router.get("/shop/orders/{order_id}", response_model=OrderOut)
async def read_order(
    order_id: OrderId, customer: dict = Depends(get_limited_customer), svc: ShopCheckout = Depends(get_checkout)
) -> OrderOut:
    return await svc.get(customer["_id"], order_id)
