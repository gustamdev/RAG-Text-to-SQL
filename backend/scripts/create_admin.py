"""Cria (ou promove) um administrador do Olist Insights.

Uso (a partir de backend/):
    uv run python scripts/create_admin.py voce@email.com "Seu Nome"

A senha é lida de forma interativa (não aparece no histórico do shell). Se o e-mail já
existir, a conta é promovida a admin e a senha é mantida. Admin nunca é criado pela API:
não existe auto-cadastro.
"""

import asyncio
import getpass
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pymongo import AsyncMongoClient  # noqa: E402

from app.auth.security import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.core.timeutil import now  # noqa: E402
from app.database.indexes import ensure_indexes  # noqa: E402
from app.database.repos.users import UserRepo  # noqa: E402


async def main(email: str, name: str) -> None:
    email = email.strip().lower()
    client = AsyncMongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    db = client[settings.MONGO_DB_NAME]
    try:
        await ensure_indexes(db)
        users = UserRepo(db)
        existing = await users.get_by_email(email)
        if existing:
            await users.promote_to_admin(existing["_id"])
            print(f"Conta existente promovida a admin: {email}")
            return
        password = getpass.getpass("Senha (8 a 128 caracteres): ")
        if not 8 <= len(password) <= 128:
            sys.exit("A senha precisa ter de 8 a 128 caracteres.")
        if password != getpass.getpass("Repita a senha: "):
            sys.exit("As senhas não conferem.")
        doc = {
            "_id": uuid.uuid4().hex,
            "name": name.strip(),
            "email": email,
            "password_hash": hash_password(password),
            "role": "admin",
            "created_at": now(),
        }
        await users.create(doc)
        print(f"Admin criado: {email}")
    finally:
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
