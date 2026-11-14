import asyncio
import logging
from contextlib import asynccontextmanager

import duckdb
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient

from app.agent_graph import build_agent_graph
from app.api.routes import (
    auth,
    backoffice,
    chat,
    health,
    products,
    shop_account,
    shop_auth,
    shop_cart,
    shop_catalog,
    shop_checkout,
)
from app.config import settings
from app.core.errors import DomainError, domain_error_handler
from app.core.logging import mask_uri, setup_logging
from app.core.rate_limit import FailureLimiter
from app.database.connection import close_db, get_database, init_db
from app.database.container import start_mongo_container
from app.database.indexes import ensure_indexes
from app.database.seed_mongo import is_seeded, seed_database
from app.database.sql_engine import SQLEngine, build_snapshot
from app.llm_models import ValidationModel
from app.services.agent_runner import AgentRunner
from app.services.catalog import CatalogService
from app.services.memory import MemoryService
from app.services.query_runner import QueryRunner
from app.services.snapshot import SnapshotService
from app.sql_guard import SHOP_VIEW_TABLES

API_VERSION = "v1"

setup_logging()
logger = logging.getLogger(__name__)


def _build_snapshot() -> bool:
    with MongoClient(settings.MONGO_URI) as client:
        return build_snapshot(client, settings.duckdb_path)


async def _prepare_data() -> None:
    # Seed e snapshot são ETL síncrono com pandas (CPU-bound, rodam uma vez): ficam numa
    # thread com client síncrono próprio em vez de serem reescritos em async.
    with MongoClient(settings.MONGO_URI) as client:
        seeded_now = False
        if not await asyncio.to_thread(is_seeded, client):
            await asyncio.to_thread(seed_database, client)
            seeded_now = True
        # Seed novo invalida o snapshot antigo; sem seed, só gera se o arquivo não existir.
        if seeded_now or not settings.duckdb_path.exists():
            await asyncio.to_thread(build_snapshot, client, settings.duckdb_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.MONGO_AUTOSTART:
        logger.info("Iniciando container do MongoDB...")
        await asyncio.to_thread(start_mongo_container)

    await init_db()
    logger.info("Conectado ao MongoDB em %s", mask_uri(settings.MONGO_URI))

    await ensure_indexes(get_database())
    app.state.login_limiter = FailureLimiter(settings.LOGIN_MAX_FAILURES, settings.LOGIN_WINDOW_S)

    await _prepare_data()

    engine = SQLEngine(
        settings.duckdb_path, timeout_s=settings.SQL_QUERY_TIMEOUT_S, max_concurrent=settings.SQL_MAX_CONCURRENT
    )
    if settings.duckdb_path.exists():
        try:
            engine.open()
        except duckdb.Error:
            # Snapshot corrompido não derruba a API: o motor fica indisponível e o resto segue.
            logger.exception("Falha ao abrir %s: motor SQL indisponível.", settings.duckdb_path)
    else:
        logger.warning("Snapshot DuckDB ausente: motor SQL indisponível.")
    query_runner = QueryRunner(engine, ttl_s=settings.QUERY_RESULT_TTL_S, max_results=settings.QUERY_RESULT_MAX)
    app.state.query_runner = query_runner

    # ValidationModel própria para o catálogo: é uma tarefa de extração estruturada, como as
    # que o optimizer/metadados já usam (llm_models.py), não a de gerar SQL nem a de texto livre.
    catalog_service = CatalogService(
        get_database(), ValidationModel().build(), known_tables=engine.tables, engine=engine
    )
    snapshot_service = SnapshotService(
        engine, _build_snapshot, debounce_s=settings.SNAPSHOT_DEBOUNCE_S, on_swap=catalog_service.update_tables
    )
    app.state.snapshot_service = snapshot_service
    if not SHOP_VIEW_TABLES <= engine.tables:  # snapshot anterior à E7: sem as views da loja
        await snapshot_service.refresh()
    memory_service = MemoryService(
        ValidationModel().build(),  # instância própria, não compartilhada — mesmo padrão de optimizer_llm/sql_llm
        max_turns=settings.MEMORY_TURNS_PER_CONSOLIDATION,
        context_max_tokens=settings.MEMORY_CONTEXT_MAX_TOKENS,
        ttl_s=settings.MEMORY_SESSION_TTL_S,
        max_sessions=settings.MEMORY_SESSION_MAX,
    )
    app.state.agent_runner = AgentRunner(
        build_agent_graph(catalog_service, query_runner),
        memory_service,
        ttl_s=settings.CHAT_RESULT_TTL_S,
        max_results=settings.CHAT_RESULT_MAX,
    )

    yield

    await snapshot_service.aclose()
    engine.close()
    await close_db()
    logger.info("Conexão com o MongoDB encerrada")


app = FastAPI(
    title="Olist Insights API",
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None if settings.is_prod else "/redoc",
    openapi_url=None if settings.is_prod else "/openapi.json",
    lifespan=lifespan,
)
app.add_exception_handler(DomainError, domain_error_handler)

allowed_origins = [origin.strip() for origin in settings.CORS_EXTRA_ORIGINS.split(",") if origin.strip()]
if not settings.is_prod:
    allowed_origins.append("http://localhost:5173")

# Middlewares próprios entram antes; o CORS, registrado por último, fica por fora de todos.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

api_prefix = f"/api/{API_VERSION}"
app.include_router(health.router, prefix=api_prefix)
app.include_router(chat.router, prefix=api_prefix)  # só admin
app.include_router(auth.router, prefix=api_prefix)
app.include_router(products.router, prefix=api_prefix)  # público
app.include_router(backoffice.router, prefix=api_prefix)  # só admin
for _shop_router in (shop_auth, shop_catalog, shop_cart, shop_checkout, shop_account):  # público/cliente, aud=shop
    app.include_router(_shop_router.router, prefix=api_prefix)
