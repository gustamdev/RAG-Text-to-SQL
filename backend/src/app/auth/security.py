"""Hash de senha (argon2id) e emissão/validação de JWT. Sem acesso a banco: funções puras."""

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

ALGORITHM = "HS256"
AUD_ADMIN = "admin"
AUD_SHOP = "shop"
_hasher = PasswordHasher()

# Hash descartável para equalizar o tempo de resposta quando o e-mail não existe
# (evita enumerar contas pela diferença de latência no login).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, password) and stored_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def _signing_key(aud: str) -> bytes:
    """Chave por audiência derivada do JWT_SECRET: token da loja nunca valida no admin (nem o inverso)."""
    return hmac.new(settings.JWT_SECRET.get_secret_value().encode(), f"jwt-aud:{aud}".encode(), hashlib.sha256).digest()


def create_access_token(user_id: str, role: str, aud: str = AUD_ADMIN, token_version: int = 0) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "aud": aud,
        "jti": uuid.uuid4().hex,
        "tv": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _signing_key(aud), algorithm=ALGORITHM)


def decode_access_token(token: str, aud: str) -> dict | None:
    try:
        return jwt.decode(
            token,
            _signing_key(aud),
            algorithms=[ALGORITHM],
            audience=aud,
            options={"require": ["sub", "exp", "jti", "aud"]},
        )
    except jwt.PyJWTError:
        return None
