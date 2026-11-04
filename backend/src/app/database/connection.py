import asyncio

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings

# O padrão do pymongo é 30 s: com o banco fora, o /health ficaria pendurado esse tempo todo.
SERVER_SELECTION_TIMEOUT_MS = 3000

# Criado no lifespan, nunca no import: os testes importam o app sem conectar.
_client: AsyncMongoClient | None = None


async def wait_for_mongo(client: AsyncMongoClient, retries: int = 10, delay: float = 1.0) -> None:
    for attempt in range(retries):
        try:
            await client.admin.command("ping")
            return
        except Exception:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(delay)


async def init_db() -> None:
    global _client
    _client = AsyncMongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS)
    await wait_for_mongo(_client)


async def close_db() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_database() -> AsyncDatabase:
    if _client is None:
        raise RuntimeError("Conexão com o MongoDB não inicializada.")
    return _client[settings.MONGO_DB_NAME]
