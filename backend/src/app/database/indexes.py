import logging

from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure

from app.config import settings

logger = logging.getLogger(__name__)

DAY_S = 86400


_OPTIONS_CONFLICT_CODES = {85, 86}  # IndexOptionsConflict, IndexKeySpecsConflict


async def _index(db: AsyncDatabase, col: str, keys, **opts) -> None:
    """create_index; se um TTL existente tem outro expireAfterSeconds, ajusta com collMod (nunca derruba o start)."""
    spec = [(keys, 1)] if isinstance(keys, str) else keys
    try:
        await db[col].create_index(spec, **opts)
    except OperationFailure as exc:
        if exc.code not in _OPTIONS_CONFLICT_CODES:
            raise
        if "expireAfterSeconds" not in opts:
            # Opções (ex.: unique) mudaram entre versões: o índice é nosso, então recria.
            # shortcut: se já houver duplicata, o create_index falha e o start para; limpar os dados e reiniciar.
            name = next(n for n, i in (await db[col].index_information()).items() if i["key"] == spec)
            logger.warning("Índice %s.%s mudou (%s): recriando.", col, name, exc)
            await db[col].drop_index(name)
            await db[col].create_index(spec, **opts)
            return
        logger.warning("TTL de %s mudou (%s): aplicando collMod.", col, exc)
        try:
            await db.command(
                {"collMod": col, "index": {"keyPattern": dict(spec), "expireAfterSeconds": opts["expireAfterSeconds"]}}
            )
        except OperationFailure as exc2:
            logger.warning("collMod falhou em %s (%s): recriando o índice.", col, exc2)
            try:
                name = next(n for n, i in (await db[col].index_information()).items() if i["key"] == spec)
                await db[col].drop_index(name)
                await db[col].create_index(spec, **opts)
            except Exception:
                logger.warning("Não foi possível atualizar o TTL de %s; mantendo o existente.", col, exc_info=True)


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Idempotente: roda a cada start. Os índices únicos são a garantia real (e-mail, idempotência).

    Os TTL apagam o documento depois do campo de data + expireAfterSeconds. Mudar um TTL já criado
    exige recriar o índice (o Mongo recusa opções diferentes para o mesmo nome).
    """
    await _index(db, "users", "email", unique=True)
    await _index(db, "chat_threads", [("user_id", 1), ("updated_at", -1)])  # lista de conversas do admin

    await _index(db, "shop_customers", "email", unique=True)
    # Conta não verificada some em 24 h: `pending_expires_at` só existe até o verify (TTL ignora quem não tem o campo).
    await _index(db, "shop_customers", "pending_expires_at", expireAfterSeconds=0)
    # Igual ao do seed (seed_mongo.py agrega geolocation a 1 linha por prefixo): opções diferentes derrubam o start.
    await _index(db, "geolocation", "geolocation_zip_code_prefix", unique=True)
    await _index(db, "shop_otp", "expires_at", expireAfterSeconds=0)
    await _index(db, "shop_otp", [("email", 1), ("purpose", 1)], unique=True)
    await _index(db, "shop_carts", "customer_id", unique=True)
    await _index(db, "shop_carts", "updated_at", expireAfterSeconds=settings.SHOP_CART_TTL_DAYS * DAY_S)
    await _index(db, "shop_addresses", "customer_id")
    # Único por (cliente, fingerprint): garante "sem duplicata" sob corrida e atende a busca por customer_id (prefixo).
    await _index(db, "shop_cards", [("customer_id", 1), ("fingerprint", 1)], unique=True)
    await _index(db, "shop_products", "product_id", unique=True)
    for field in ("category", "units_sold", "price_cents", "avg_rating", "created_at"):  # sort e filtro da listagem
        await _index(db, "shop_products", field)
    # Sorts da listagem (SORTS + desempate product_id): um composto por ordenação.
    for sort in (
        [("units_sold", -1)], [("price_cents", 1)], [("price_cents", -1)],
        [("avg_rating", -1), ("review_count", -1)], [("created_at", -1)],
    ):  # fmt: skip
        await _index(db, "shop_products", sort + [("product_id", 1)])
    await _index(db, "shop_orders", "created_at")  # sort do admin_page
    await _index(db, "shop_orders", [("customer_id", 1), ("created_at", -1)])
    await _index(db, "shop_orders", "order_id", unique=True)
    await _index(db, "shop_orders", [("state", 1), ("reservation_expires_at", 1)])
    await _index(db, "shop_orders", "payment_id")
    await _index(db, "shop_payments", "order_id", unique=True)
    await _index(db, "shop_payments", "payment_id")
    await _index(db, "shop_idempotency", [("customer_id", 1), ("scope", 1), ("key", 1)], unique=True)
    await _index(db, "shop_idempotency", "created_at", expireAfterSeconds=DAY_S)
    await _index(
        db, "shop_audit", "created_at", expireAfterSeconds=365 * DAY_S
    )  # rede de segurança p/ docs sem expires_at
    await _index(db, "shop_audit", "expires_at", expireAfterSeconds=0)
    await _index(db, "shop_customers", "created_at")
    logger.info("Índices garantidos.")
