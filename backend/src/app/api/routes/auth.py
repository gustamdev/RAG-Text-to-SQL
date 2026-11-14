from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import Repos, get_current_user, get_login_limiter, get_repos
from app.core.rate_limit import FailureLimiter
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.services import auth_service
from app.services.mappers import user_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    repos: Repos = Depends(get_repos),
    limiter: FailureLimiter = Depends(get_login_limiter),
) -> TokenResponse:
    ip = request.client.host if request.client else "unknown"
    return await auth_service.login(repos.users, limiter, payload, ip)


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)) -> UserOut:
    return user_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: dict = Depends(get_current_user), repos: Repos = Depends(get_repos)) -> Response:
    await repos.users.bump_token_version(user["_id"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
