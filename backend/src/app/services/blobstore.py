"""Blob storage local (simula container/blob do S3/Azure): `<BLOBSTORE_DIR>/<container>/<blob>`.

Imagens vivem em disco e o Mongo guarda só a chave ("product-images/<id>.jpg"), nunca base64.
Trocar por S3/Azure depois = reescrever esta classe (put/path_of/exists/url); chamadores só usam esses 4.
"""

import os
import re
import uuid
from pathlib import Path

from app.config import settings

CONTAINER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
BLOB_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.(jpg|jpeg|png|webp)$")
MAX_BYTES = 2 * 1024 * 1024
CONTENT_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class BlobError(ValueError):
    """Nome inválido, tipo errado, arquivo grande demais ou fora do diretório base."""


def _is_image(ext: str, data: bytes) -> bool:
    if ext in ("jpg", "jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    if ext == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


class BlobStore:
    def __init__(self, base: Path, base_url: str):
        self.base, self.base_url = base.resolve(), base_url.rstrip("/")

    def path_of(self, container: str, name: str) -> Path:
        if not CONTAINER_RE.fullmatch(container) or not BLOB_RE.fullmatch(name) or ".." in name:
            raise BlobError("Nome de container/blob inválido.")
        path = (self.base / container / name).resolve()
        if not path.is_relative_to(self.base):  # symlink apontando para fora
            raise BlobError("Caminho fora do diretório base.")
        return path

    def exists(self, container: str, name: str) -> bool:
        try:
            return self.path_of(container, name).is_file()
        except BlobError:
            return False

    def url(self, container: str, name: str) -> str:
        self.path_of(container, name)  # valida
        return f"{self.base_url}/{container}/{name}"

    def put(self, container: str, name: str, data: bytes, content_type: str) -> str:
        path = self.path_of(container, name)
        ext = name.rsplit(".", 1)[1]
        if CONTENT_TYPES[ext] != content_type:
            raise BlobError("content_type não bate com a extensão.")
        if len(data) > MAX_BYTES:
            raise BlobError("Arquivo acima do limite.")
        if not _is_image(ext, data):
            raise BlobError("Conteúdo não é uma imagem do tipo declarado.")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{uuid.uuid4().hex}.tmp")  # escrita atômica: leitor nunca vê arquivo pela metade
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return self.url(container, name)


store = BlobStore(settings.blobstore_dir, settings.MEDIA_BASE_URL)
