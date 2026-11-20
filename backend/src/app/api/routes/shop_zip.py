"""CEP -> endereço público. O servidor consulta BrasilAPI/ViaCEP (com cache) e cai no prefixo offline."""

from fastapi import APIRouter, Depends, Response
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import enforce_zip_rate_limit, get_app_db
from app.api.shop_params import ZipPath
from app.core.errors import NotFound
from app.database.repos.geolocation import GeolocationRepo
from app.schemas.shop_store import ZipOut
from app.services.zip_lookup import ZipRemote, lookup_zip, zip_remote

router = APIRouter(prefix="/shop/zip", tags=["shop-catalog"], dependencies=[Depends(enforce_zip_rate_limit)])


def get_zip_remote() -> ZipRemote:
    return zip_remote


@router.get("/{zip}", response_model=ZipOut)
async def get_zip(
    zip: ZipPath,
    response: Response,
    db: AsyncDatabase = Depends(get_app_db),
    remote: ZipRemote = Depends(get_zip_remote),
) -> ZipOut:
    info = await lookup_zip(zip, GeolocationRepo(db), remote)
    if info is None:
        raise NotFound("CEP não encontrado.")
    response.headers["Cache-Control"] = f"public, max-age={300 if info.source == 'offline' else 3600}"
    return info
