from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from app.api.deps import enforce_public_rate_limit
from app.api.shop_deps import get_current_customer, get_shop_auth_service
from app.schemas.shop_auth import (
    CustomerOut,
    DetailOut,
    MfaRequiredOut,
    ResendOtpRequest,
    ShopLoginRequest,
    ShopTokenResponse,
    SignupRequest,
    VerifyOtpRequest,
)
from app.services.shop_auth_service import ShopAuthService, customer_out

router = APIRouter(prefix="/shop/auth", tags=["shop-auth"])
_public = [Depends(enforce_public_rate_limit)]


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/signup", status_code=status.HTTP_202_ACCEPTED, response_model=DetailOut, dependencies=_public)
async def signup(
    payload: SignupRequest, request: Request, bg: BackgroundTasks, svc: ShopAuthService = Depends(get_shop_auth_service)
) -> DetailOut:
    return DetailOut(detail=await svc.signup(payload, _ip(request), bg.add_task))


@router.post("/verify-otp", response_model=ShopTokenResponse, dependencies=_public)
async def verify_otp(
    payload: VerifyOtpRequest, request: Request, svc: ShopAuthService = Depends(get_shop_auth_service)
) -> ShopTokenResponse:
    return await svc.verify_signup(payload, _ip(request))


@router.post("/resend-otp", status_code=status.HTTP_202_ACCEPTED, response_model=DetailOut, dependencies=_public)
async def resend_otp(
    payload: ResendOtpRequest,
    request: Request,
    bg: BackgroundTasks,
    svc: ShopAuthService = Depends(get_shop_auth_service),
) -> DetailOut:
    return DetailOut(detail=await svc.resend(payload, _ip(request), bg.add_task))


@router.post("/login", status_code=status.HTTP_202_ACCEPTED, response_model=MfaRequiredOut, dependencies=_public)
async def login(
    payload: ShopLoginRequest,
    request: Request,
    bg: BackgroundTasks,
    svc: ShopAuthService = Depends(get_shop_auth_service),
) -> MfaRequiredOut:
    return await svc.login(payload, _ip(request), bg.add_task)


@router.post("/login/verify-otp", response_model=ShopTokenResponse, dependencies=_public)
async def login_verify_otp(
    payload: VerifyOtpRequest, request: Request, svc: ShopAuthService = Depends(get_shop_auth_service)
) -> ShopTokenResponse:
    return await svc.verify_login(payload, _ip(request))


@router.get("/me", response_model=CustomerOut)
async def me(customer: dict = Depends(get_current_customer)) -> CustomerOut:
    return customer_out(customer)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    customer: dict = Depends(get_current_customer),
    svc: ShopAuthService = Depends(get_shop_auth_service),
) -> Response:
    await svc.logout(customer, _ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
