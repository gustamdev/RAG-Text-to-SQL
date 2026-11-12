"""Documentos do Mongo -> schemas da API. Único lugar que conhece o formato dos documentos."""

from app.core.timeutil import iso
from app.schemas.auth import UserOut


def user_out(doc: dict) -> UserOut:
    return UserOut(
        id=doc["_id"],
        name=doc["name"],
        email=doc["email"],
        role=doc["role"],
        created_at=iso(doc["created_at"]),
    )
