from fastapi import APIRouter, Depends, Response, status
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def health(response: Response, db: AsyncDatabase = Depends(get_db)) -> HealthResponse:
    try:
        await db.command("ping")
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", database="unavailable")
    return HealthResponse(status="ok", database="ok")
