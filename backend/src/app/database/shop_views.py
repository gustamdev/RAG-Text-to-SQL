"""Views projetadas da loja para o agente (E7): ALLOWLIST de colunas, sem PII.

O agente nunca lê `shop_*` bruto. Cada tabela abaixo é gravada no snapshot DuckDB a partir de uma
projeção explícita: pseudônimo do cliente (HMAC), ids de pedido/produto, status, data no dia,
valores em centavos, categoria, UF e prefixo de CEP de 3 dígitos, bandeira do cartão. Fora da lista
nada passa: nome, apelido, e-mail, endereço textual, últimos 4 e texto livre não têm coluna.
Todo valor é validado por regex/enum e vira NULL se não casar (defesa contra texto digitado).
"""

import re
from collections.abc import Iterable, Iterator
from datetime import date, datetime
from itertools import batched
from typing import Any

import duckdb
from pymongo.database import Database

from app.services.shop_auth_service import pseudo
from app.sql_guard import SHOP_VIEW_TABLES

BATCH_SIZE = 5000

# nome da coluna -> tipo DuckDB. A ordem é a ordem das tuplas produzidas por cada linha abaixo.
VIEW_COLUMNS: dict[str, dict[str, str]] = {
    "shop_orders_view": {
        "order_id": "VARCHAR",
        "customer_pseudo": "VARCHAR",
        "status": "VARCHAR",
        "order_date": "DATE",
        "items_qty": "INTEGER",
        "subtotal_cents": "BIGINT",
        "freight_cents": "BIGINT",
        "discount_cents": "BIGINT",
        "total_cents": "BIGINT",
        "shipping_option": "VARCHAR",
        "destination_state": "VARCHAR",
        "destination_zip3": "VARCHAR",
    },
    "shop_order_items_view": {
        "order_id": "VARCHAR",
        "order_date": "DATE",
        "product_id": "VARCHAR",
        "category": "VARCHAR",
        "qty": "INTEGER",
        "unit_price_cents": "BIGINT",
        "line_total_cents": "BIGINT",
    },
    "shop_payments_view": {
        "payment_id": "VARCHAR",
        "order_id": "VARCHAR",
        "customer_pseudo": "VARCHAR",
        "status": "VARCHAR",
        "card_brand": "VARCHAR",
        "installments": "INTEGER",
        "amount_cents": "BIGINT",
        "payment_date": "DATE",
    },
    "shop_customers_view": {
        "customer_pseudo": "VARCHAR",
        "signup_date": "DATE",
        "last_login_date": "DATE",
        "state": "VARCHAR",
        "zip3": "VARCHAR",
    },
}
assert set(VIEW_COLUMNS) == SHOP_VIEW_TABLES

_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_SLUG = re.compile(r"[a-z0-9_]{1,80}")
_UF = re.compile(r"[A-Z]{2}")
_ZIP3 = re.compile(r"\d{3}")
_ORDER_STATES = {"created", "paid", "refused", "shipped", "delivered", "canceled"}
_PAYMENT_STATES = {"approved", "refused", "timeout"}
_SHIPPING = {"standard", "economy"}


def _match(pattern: re.Pattern[str], value: Any) -> str | None:
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def _enum(allowed: set[str], value: Any) -> str | None:
    return value if value in allowed else None


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _zip3(value: Any) -> str | None:
    digits = re.sub(r"\D", "", value) if isinstance(value, str) else ""
    return digits[:3] if len(digits) >= 3 else None


def _customer_pseudo(customer_id: Any, deleted: set[str]) -> str | None:
    # Conta apagada (ou apagada logicamente, antes da purga) some do agente: vira NULL, não o pseudônimo.
    if not isinstance(customer_id, str) or customer_id in deleted:
        return None
    return pseudo(f"agent-view:{customer_id}")  # prefixo: não casa com o pseudônimo da auditoria


def _order_row(doc: dict, deleted: set[str]) -> tuple:
    address = doc.get("address") or {}
    shipping = doc.get("shipping") or {}
    items = doc.get("items") or []
    return (
        _match(_ID, doc.get("order_id")),
        _customer_pseudo(doc.get("customer_id"), deleted),
        _enum(_ORDER_STATES, doc.get("state")),
        _day(doc.get("created_at")),
        sum(q for item in items if (q := _int(item.get("qty"))) is not None),
        _int(doc.get("subtotal_cents")),
        _int(doc.get("freight_cents")),
        _int(doc.get("discount_cents")),
        _int(doc.get("total_cents")),
        _enum(_SHIPPING, shipping.get("option")),
        _match(_UF, address.get("state")),
        _zip3(address.get("zip")),
    )


def _item_rows(doc: dict) -> Iterator[tuple]:
    for item in doc.get("items") or []:
        yield (
            _match(_ID, doc.get("order_id")),
            _day(doc.get("created_at")),
            _match(_ID, item.get("product_id")),
            _match(_SLUG, item.get("category")),
            _int(item.get("qty")),
            _int(item.get("unit_price_cents")),
            _int(item.get("line_total_cents")),
        )


def _payment_row(doc: dict, deleted: set[str]) -> tuple:
    return (
        _match(_ID, doc.get("payment_id")),
        _match(_ID, doc.get("order_id")),
        _customer_pseudo(doc.get("customer_id"), deleted),
        _enum(_PAYMENT_STATES, doc.get("status")),
        _match(_SLUG, (doc.get("brand") or "").lower() if isinstance(doc.get("brand"), str) else None),
        _int(doc.get("installments")),
        _int(doc.get("amount_cents")),
        _day(doc.get("created_at")),
    )


def _insert(con: duckdb.DuckDBPyConnection, table: str, rows: Iterable[tuple]) -> int:
    columns = VIEW_COLUMNS[table]
    placeholders = ", ".join("?" * len(columns))
    total = 0
    for batch in batched(rows, BATCH_SIZE, strict=False):
        con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", [list(row) for row in batch])
        total += len(batch)
    return total


def _stream(db: Database, collection: str, projection: list[str], query: dict | None = None) -> Iterator[dict]:
    return db[collection].find(query or {}, {"_id": 0, **dict.fromkeys(projection, 1)})


def write_shop_views(db: Database, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Cria e preenche as views da loja no snapshot em construção. Lê o Mongo em fluxo, em lotes."""
    for table, columns in VIEW_COLUMNS.items():
        con.execute(f"CREATE TABLE {table} ({', '.join(f'{name} {kind}' for name, kind in columns.items())})")

    # `_id` é a chave do cliente; só ele e deleted_at saem desta consulta, para filtrar contas apagadas.
    deleted = {
        doc["_id"]
        for doc in db["shop_customers"].find({"deleted_at": {"$nin": [None, False]}}, {"_id": 1})
        if isinstance(doc.get("_id"), str)
    }

    order_fields = ["order_id", "customer_id", "state", "created_at", "items", "subtotal_cents", "freight_cents"]
    order_fields += ["discount_cents", "total_cents", "shipping.option", "address.state", "address.zip"]
    counts: dict[str, int] = {}

    def orders() -> Iterator[dict]:
        return _stream(db, "shop_orders", order_fields)

    counts["shop_orders_view"] = _insert(con, "shop_orders_view", (_order_row(d, deleted) for d in orders()))
    counts["shop_order_items_view"] = _insert(
        con, "shop_order_items_view", (row for d in orders() for row in _item_rows(d))
    )
    payment_fields = ["payment_id", "order_id", "customer_id", "status", "brand", "installments", "amount_cents"]
    counts["shop_payments_view"] = _insert(
        con,
        "shop_payments_view",
        (_payment_row(d, deleted) for d in _stream(db, "shop_payments", payment_fields + ["created_at"])),
    )

    # UF/zip3 do endereço padrão (ou do primeiro): só o necessário é lido, o texto do endereço nunca sai daqui.
    places: dict[str, tuple[str | None, str | None]] = {}
    for addr in _stream(db, "shop_addresses", ["customer_id", "state", "zip", "is_default"]):
        cid = addr.get("customer_id")
        if isinstance(cid, str) and (cid not in places or addr.get("is_default")):
            places[cid] = (_match(_UF, addr.get("state")), _zip3(addr.get("zip")))

    def customers() -> Iterator[tuple]:
        query = {"deleted_at": {"$in": [None, False]}, "email_verified": True}
        for doc in db["shop_customers"].find(query, {"_id": 1, "created_at": 1, "last_login_at": 1}):
            state, zip3 = places.get(doc["_id"], (None, None))
            yield (
                _customer_pseudo(doc["_id"], deleted),
                _day(doc.get("created_at")),
                _day(doc.get("last_login_at")),
                state,
                zip3,
            )

    counts["shop_customers_view"] = _insert(con, "shop_customers_view", customers())
    return counts
