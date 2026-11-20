from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from app.api.deps import enforce_auth_rate_limit
from app.api.shop_deps import get_limited_customer, get_shop_auth_service
from app.core.rate_limit import ip_key
from app.schemas.shop_auth import (
    CustomerOut,
    DetailOut,
    ForgotPasswordOut,
    ForgotPasswordRequest,
    MfaRequiredOut,
    OkOut,
    ResendOtpRequest,
    ResetPasswordRequest,
    ShopLoginRequest,
    ShopTokenResponse,
    SignupRequest,
    VerifyOtpRequest,
)
from app.services.shop_auth_service import ShopAuthService, customer_out

router = APIRouter(prefix="/shop/auth", tags=["shop-auth"])
_public = [Depends(enforce_auth_rate_limit)]


def _ip(request: Request) -> str:
    return ip_key(request.client.host) if request.client else "unknown"  # IPv6 = /64: limites OTP/login por rede


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


@router.post(
    "/forgot-password", status_code=status.HTTP_202_ACCEPTED, response_model=ForgotPasswordOut, dependencies=_public
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    bg: BackgroundTasks,
    svc: ShopAuthService = Depends(get_shop_auth_service),
) -> ForgotPasswordOut:
    return ForgotPasswordOut(**await svc.forgot_password(payload, _ip(request), bg.add_task))


@router.post("/reset-password", response_model=OkOut, dependencies=_public)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    bg: BackgroundTasks,
    svc: ShopAuthService = Depends(get_shop_auth_service),
) -> OkOut:
    await svc.reset_password(payload, _ip(request), bg.add_task)
    return OkOut()


@router.get("/me", response_model=CustomerOut)
async def me(customer: dict = Depends(get_limited_customer)) -> CustomerOut:
    return customer_out(customer)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    customer: dict = Depends(get_limited_customer),
    svc: ShopAuthService = Depends(get_shop_auth_service),
) -> Response:
    await svc.logout(customer)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
