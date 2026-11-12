import logging

from pymongo.asynchronous.database import AsyncDatabase

logger = logging.getLogger(__name__)


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Idempotente: roda a cada start. O índice único é a garantia real contra e-mail duplicado."""
    await db["users"].create_index("email", unique=True)
    logger.info("Índices de usuários garantidos.")
