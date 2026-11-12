import logging
import shutil
import urllib.request
from pathlib import Path

import pandas as pd
from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.config import settings

logger = logging.getLogger(__name__)

MONGO_DB_NAME = settings.MONGO_DB_NAME
OLIST_BASE_URL = settings.OLIST_BASE_URL
DATASET_DIR = settings.dataset_dir

BATCH_SIZE = 5000
SEED_YEAR = settings.SEED_YEAR  # None = todos os anos
DOWNLOAD_TIMEOUT = 60

CSV_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "product_category_name_translation": "product_category_name_translation.csv",
}

ZIP_CODE_COLUMNS = {
    "customers": "customer_zip_code_prefix",
    "sellers": "seller_zip_code_prefix",
    "geolocation": "geolocation_zip_code_prefix",
}

DATE_COLUMNS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}

INT_COLUMNS = {
    "order_items": ["order_item_id"],
    "order_payments": ["payment_sequential", "payment_installments"],
    "order_reviews": ["review_score"],
    "products": ["product_name_length", "product_description_length", "product_photos_qty"],
}

FLOAT_COLUMNS = {
    "order_items": ["price", "freight_value"],
    "order_payments": ["payment_value"],
    "products": ["product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"],
}

RENAMED_COLUMNS = {
    "products": {
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    },
}

UNIQUE_INDEXES = {
    "customers": [["customer_id"]],
    "geolocation": [["geolocation_zip_code_prefix"]],
    "orders": [["order_id"]],
    "order_items": [["order_id", "order_item_id"]],
    "order_payments": [["order_id", "payment_sequential"]],
    "order_reviews": [["review_id", "order_id"]],
    "products": [["product_id"]],
    "sellers": [["seller_id"]],
    "product_category_name_translation": [["product_category_name"]],
}

LOOKUP_INDEXES = {
    "customers": ["customer_unique_id", "customer_zip_code_prefix"],
    "orders": ["customer_id", "order_purchase_timestamp", "order_status"],
    "order_items": ["product_id", "seller_id"],
    "order_payments": ["order_id"],
    "order_reviews": ["order_id"],
    "products": ["product_category_name"],
    "sellers": ["seller_zip_code_prefix"],
}

# orders por último: ela é o sentinela de "seed completo"
INSERT_ORDER = [name for name in CSV_FILES if name != "orders"] + ["orders"]


def _required_columns(collection: str) -> set[str]:
    columns = {field for fields in UNIQUE_INDEXES[collection] for field in fields}
    columns.update(LOOKUP_INDEXES.get(collection, []))
    for table in (DATE_COLUMNS, INT_COLUMNS, FLOAT_COLUMNS):
        columns.update(table.get(collection, []))
    return columns


def _csv_is_valid(collection: str) -> bool:
    path = DATASET_DIR / CSV_FILES[collection]
    try:
        header = pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns
    except (OSError, ValueError) as exc:
        logger.warning("CSV ilegível (%s): %s", path.name, exc)
        return False

    renamed = RENAMED_COLUMNS.get(collection, {})
    missing = _required_columns(collection) - {renamed.get(column, column) for column in header}
    if missing:
        logger.warning("CSV %s sem as colunas esperadas: %s", path.name, sorted(missing))
    return not missing


def _fetch_csv(collection: str) -> bool:
    filename = CSV_FILES[collection]
    url = f"{OLIST_BASE_URL}/{filename}"
    path = DATASET_DIR / filename
    partial_path = path.with_name(f"{filename}.part")

    logger.info("  baixando %s", filename)
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
            with open(partial_path, "wb") as file:
                shutil.copyfileobj(response, file)
    except OSError as exc:
        partial_path.unlink(missing_ok=True)
        logger.error("Falha ao baixar %s: %s", url, exc)
        return False

    partial_path.replace(path)
    if not _csv_is_valid(collection):
        path.unlink()
        logger.error("Arquivo baixado de %s não é um CSV válido do Olist.", url)
        return False
    return True


def _download_dataset() -> Path | None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    for collection, filename in CSV_FILES.items():
        path = DATASET_DIR / filename
        if path.exists():
            if _csv_is_valid(collection):
                continue
            logger.warning("CSV local inválido, será baixado de novo: %s", filename)
            path.unlink()
        if not _fetch_csv(collection):
            logger.error("Seed do Olist abortado: dataset incompleto.")
            return None
    return DATASET_DIR


def _read_csv(dataset_dir: Path, collection: str) -> pd.DataFrame:
    zip_column = ZIP_CODE_COLUMNS.get(collection)
    df = pd.read_csv(
        dataset_dir / CSV_FILES[collection],
        encoding="utf-8-sig",
        dtype={zip_column: str} if zip_column else None,
    )

    df = df.rename(columns=RENAMED_COLUMNS.get(collection, {}))
    if zip_column:
        df[zip_column] = df[zip_column].str.zfill(5)
    for column in DATE_COLUMNS.get(collection, []):
        df[column] = pd.to_datetime(df[column], errors="coerce")
    for column in INT_COLUMNS.get(collection, []):
        df[column] = df[column].astype("Int64")
    for column in FLOAT_COLUMNS.get(collection, []):
        df[column] = df[column].astype(float)
    return df


def _load_frames(dataset_dir: Path) -> dict[str, pd.DataFrame]:
    return {collection: _read_csv(dataset_dir, collection) for collection in CSV_FILES}


def _aggregate_geolocation(geolocation: pd.DataFrame) -> pd.DataFrame:
    return geolocation.groupby("geolocation_zip_code_prefix", as_index=False).agg(
        geolocation_lat=("geolocation_lat", "mean"),
        geolocation_lng=("geolocation_lng", "mean"),
        geolocation_city=("geolocation_city", lambda s: s.mode().iat[0]),
        geolocation_state=("geolocation_state", lambda s: s.mode().iat[0]),
    )


def _filter_by_year(frames: dict[str, pd.DataFrame], year: int | None) -> dict[str, pd.DataFrame]:
    """Recorta o dataset aos pedidos de `year` (e ao que depende deles). `year=None` mantém todos."""
    orders = frames["orders"]
    if year is not None:
        orders = orders[orders["order_purchase_timestamp"].dt.year == year]
    order_ids = orders["order_id"]

    order_items = frames["order_items"]
    order_items = order_items[order_items["order_id"].isin(order_ids)]

    order_payments = frames["order_payments"]
    order_payments = order_payments[order_payments["order_id"].isin(order_ids)]

    order_reviews = frames["order_reviews"]
    order_reviews = order_reviews[order_reviews["order_id"].isin(order_ids)].drop_duplicates(
        subset=["review_id", "order_id"]
    )

    customers = frames["customers"]
    customers = customers[customers["customer_id"].isin(orders["customer_id"])]

    products = frames["products"]
    products = products[products["product_id"].isin(order_items["product_id"])]

    sellers = frames["sellers"]
    sellers = sellers[sellers["seller_id"].isin(order_items["seller_id"])]

    zip_codes = pd.concat([customers["customer_zip_code_prefix"], sellers["seller_zip_code_prefix"]])
    geolocation = frames["geolocation"]
    geolocation = geolocation[geolocation["geolocation_zip_code_prefix"].isin(zip_codes)]

    return {
        "customers": customers,
        "geolocation": _aggregate_geolocation(geolocation),
        "orders": orders,
        "order_items": order_items,
        "order_payments": order_payments,
        "order_reviews": order_reviews,
        "products": products,
        "sellers": sellers,
        "product_category_name_translation": frames["product_category_name_translation"],
    }


def _to_documents(df: pd.DataFrame) -> list[dict]:
    documents = df.astype(object).where(df.notna(), None).to_dict("records")
    for document in documents:
        for key, value in document.items():
            if isinstance(value, pd.Timestamp):
                document[key] = value.to_pydatetime()
    return documents


def _create_indexes(db: Database) -> None:
    for collection, indexes in UNIQUE_INDEXES.items():
        for fields in indexes:
            db[collection].create_index([(field, ASCENDING) for field in fields], unique=True)
    for collection, fields in LOOKUP_INDEXES.items():
        for field in fields:
            db[collection].create_index([(field, ASCENDING)])


def _insert(db: Database, collection: str, documents: list[dict]) -> None:
    for start in range(0, len(documents), BATCH_SIZE):
        db[collection].insert_many(documents[start : start + BATCH_SIZE])
    logger.info("  %-35s %7d documentos", collection, len(documents))


def is_seeded(client: MongoClient) -> bool:
    db = client[MONGO_DB_NAME]
    counts = {collection: db[collection].estimated_document_count() for collection in CSV_FILES}
    if counts["orders"] == 0:
        return False

    empty = [collection for collection, count in counts.items() if count == 0]
    if empty:
        logger.warning(
            "Banco '%s' já possui dados, mas estas coleções estão vazias: %s. "
            "Seed ignorado para preservar os dados existentes; apague o banco para recarregar.",
            MONGO_DB_NAME,
            ", ".join(empty),
        )
    else:
        logger.info("Banco '%s' já inicializado (%d orders). Seed ignorado.", MONGO_DB_NAME, counts["orders"])
    return True


def seed_database(client: MongoClient) -> None:
    db = client[MONGO_DB_NAME]
    dataset_dir = _download_dataset()
    if dataset_dir is None:
        return

    logger.info("Carregando Olist (%s) no banco '%s'...", SEED_YEAR or "todos os anos", MONGO_DB_NAME)
    try:
        frames = _filter_by_year(_load_frames(dataset_dir), SEED_YEAR)
    except (OSError, ValueError, KeyError) as exc:
        logger.error("Falha ao ler/processar os CSVs em %s: %s", dataset_dir, exc)
        return

    if frames["orders"].empty:
        logger.error("Nenhum pedido (%s) nos CSVs. Seed abortado.", SEED_YEAR or "todos os anos")
        return

    try:
        for collection in CSV_FILES:
            db.drop_collection(collection)
        _create_indexes(db)
        for collection in INSERT_ORDER:
            _insert(db, collection, _to_documents(frames[collection]))
    except PyMongoError as exc:
        db.drop_collection("orders")  # sem orders o seed roda de novo no próximo start
        logger.error("Falha ao importar para o MongoDB: %.300s... Seed será repetido na próxima inicialização.", exc)
        return

    logger.info("Seed do Olist concluído.")
