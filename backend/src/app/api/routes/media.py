"""Leitura pública das imagens do blob storage local. Só GET/HEAD; sem listagem, sem upload."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.blobstore import CONTENT_TYPES, BlobError, store

router = APIRouter(tags=["media"])

HEADERS = {"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"}


@router.api_route("/media/{container}/{blob}", methods=["GET", "HEAD"], include_in_schema=False)
async def get_media(container: str, blob: str) -> FileResponse:
    try:
        path = store.path_of(container, blob)
    except BlobError:
        raise HTTPException(status_code=404, detail="Não encontrado.") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Não encontrado.")
    return FileResponse(path, media_type=CONTENT_TYPES[blob.rsplit(".", 1)[1]], headers=HEADERS)
