import asyncio
import logging
import time
from contextlib import asynccontextmanager

import duckdb
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.agent_graph import build_agent_graph
from app.api.routes import (
    admin_shop,
    auth,
    backoffice,
    chat,
    health,
    media,
    products,
    shop_account,
    shop_auth,
    shop_cart,
    shop_catalog,
    shop_checkout,
    shop_legal,
    shop_zip,
)
from app.config import settings
from app.core.errors import DomainError, domain_error_handler
from app.core.logging import mask_uri, setup_logging
from app.core.rate_limit import FailureLimiter
from app.database.connection import close_db, get_database, init_db
from app.database.container import start_mongo_container
from app.database.indexes import ensure_indexes
from app.database.repos.chat_threads import ChatThreadsRepo
from app.database.seed_mongo import is_seeded, seed_database
from app.database.sql_engine import SQLEngine, build_snapshot
from app.llm_models import ValidationModel
from app.services.agent_runner import AgentRunner
from app.services.catalog import CatalogService
from app.services.memory import MemoryService
from app.services.query_runner import QueryRunner
from app.services.shop_checkout import ShopCheckout
from app.services.shop_retention import ShopRetention
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


async def _expire_loop(db, refresher) -> None:
    """Devolve o estoque de reservas vencidas a cada SHOP_EXPIRE_INTERVAL_S, repete refresh pendente do
    snapshot e roda a retenção LGPD a cada SHOP_RETENTION_INTERVAL_S; nunca morre por erro."""
    svc, maint = ShopCheckout(db), ShopRetention(db, refresher)
    last_retention = time.monotonic() - settings.SHOP_RETENTION_INTERVAL_S  # roda no primeiro ciclo
    while True:
        try:
            if count := await svc.expire_reservations():
                logger.info("Reservas expiradas: %d", count)
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao expirar reservas.")
        try:
            if await maint.retry_snapshot():
                logger.info("Refresh pendente do snapshot repetido.")
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao repetir refresh do snapshot.")
        if time.monotonic() - last_retention >= settings.SHOP_RETENTION_INTERVAL_S:
            last_retention = time.monotonic()  # avança também na falha: backoff de um intervalo, não retry a cada ciclo
            try:
                logger.info("Retenção: %s", await maint.run())
            except Exception:  # noqa: BLE001
                logger.exception("Falha na retenção.")
        await asyncio.sleep(settings.SHOP_EXPIRE_INTERVAL_S)


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
        threads=ChatThreadsRepo(get_database()),
    )

    expire_task = asyncio.create_task(_expire_loop(get_database(), snapshot_service))

    yield

    expire_task.cancel()
    await asyncio.gather(expire_task, return_exceptions=True)
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


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Sem `input`/`ctx`: o 422 padrão ecoaria o corpo (PAN, CVV, senha) na resposta.
    detail = [{k: e[k] for k in ("type", "loc", "msg") if k in e} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})


async def mongo_error_handler(request: Request, exc: PyMongoError) -> JSONResponse:
    logger.error("Erro do MongoDB em %s: %s", request.url.path, type(exc).__name__)
    if "/shop" in request.url.path:
        return JSONResponse(status_code=503, content={"detail": "Serviço indisponível. Tente novamente."})
    return JSONResponse(status_code=500, content={"detail": "Erro interno."})


app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(PyMongoError, mongo_error_handler)

allowed_origins = [origin.strip() for origin in settings.CORS_EXTRA_ORIGINS.split(",") if origin.strip()]
if not settings.is_prod:
    allowed_origins.append("http://localhost:5173")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-site",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Só acrescenta o que a rota não definiu. HSTS fica no proxy TLS (docs/seguranca-loja.md)."""
    response = await call_next(request)
    if response.status_code >= 400 and request.url.path.startswith(f"{api_prefix}/shop/zip/"):
        response.headers["Cache-Control"] = "no-store"
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


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
app.include_router(admin_shop.router, prefix=api_prefix)  # só admin, PII mascarada
# público/cliente, aud=shop
for _shop_router in (shop_auth, shop_catalog, shop_zip, shop_legal, shop_cart, shop_checkout, shop_account):
    app.include_router(_shop_router.router, prefix=api_prefix)
app.include_router(media.router)  # público, fora de /api/v1: imagens do blob storage local
