import asyncio
import contextlib
import sys
import uuid
from datetime import datetime
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.deps import get_app_db, get_sql_engine  # noqa: E402
from app.auth.security import create_access_token, hash_password  # noqa: E402
from app.core.timeutil import now  # noqa: E402
from app.database.indexes import ensure_indexes  # noqa: E402
from app.database.sql_engine import SQLEngine  # noqa: E402


@pytest.fixture
def app():
    from app.main import app

    return app


def _reset_app_state(app) -> None:
    """Estado em memória que os testes (ou as dependências preguiçosas) deixam pendurado na app."""
    app.state.login_limiter = None
    app.state.chat_limiter = None
    app.state.public_limiter = None
    app.state._state.pop("query_runner", None)


@pytest.fixture
def client(app, monkeypatch):
    """TestClient com um único event loop e SEM o lifespan real (que subiria Mongo e baixaria o dataset).

    Com `with TestClient(...)` o loop vive durante o teste inteiro, então o semáforo do SQLEngine e as
    tasks em segundo plano do AgentRunner não ficam presos a um loop descartado entre requisições.
    """

    @contextlib.asynccontextmanager
    async def no_lifespan(_app):
        yield

    monkeypatch.setattr(app.router, "lifespan_context", no_lifespan)
    _reset_app_state(app)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    _reset_app_state(app)


# --- Autenticação: banco em memória (mongomock-motor) ----------------------------------------

DEFAULT_PASSWORD = "senha-forte-1"


class AuthDB:
    """Banco de usuários em memória + atalhos para criar admins e contas sem perfil admin."""

    def __init__(self, client: TestClient, db):
        self.client, self.db = client, db
        asyncio.run(ensure_indexes(db))  # o lifespan não roda nos testes; o índice único é a garantia real
        client.app.dependency_overrides[get_app_db] = lambda: db

    def run(self, coro):
        return asyncio.run(coro)

    def _insert_user(self, role: str, email: str | None, password: str) -> dict:
        doc = {
            "_id": uuid.uuid4().hex,
            "name": "Usuário Teste",
            "email": (email or f"{uuid.uuid4().hex[:8]}@teste.com").lower(),
            "password_hash": hash_password(password),
            "role": role,
            "created_at": now(),
        }
        self.run(self.db["users"].insert_one(doc))
        return doc

    @staticmethod
    def bearer(user: dict) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user['_id'], user['role'])}"}

    def create_admin(self, email: str | None = None, password: str = DEFAULT_PASSWORD):
        """Insere um admin direto no banco (como o scripts/create_admin.py) e devolve (headers, doc)."""
        user = self._insert_user("admin", email, password)
        return self.bearer(user), user

    def create_non_admin(self, role: str = "comprador", email: str | None = None, password: str = DEFAULT_PASSWORD):
        """Conta legada com papel que não existe mais (ex.: 'comprador'): deve ser barrada em tudo."""
        user = self._insert_user(role, email, password)
        return self.bearer(user), user


@pytest.fixture
def auth_db(client):
    from mongomock_motor import AsyncMongoMockClient

    return AuthDB(client, AsyncMongoMockClient()["olist_test"])


# --- Analytics: DuckDB temporário com um dataset Olist mínimo, conferido à mão ----------------

PRODUCT_A = "a1b2c3d4e5f60001"  # beleza_saude (com tradução), 5 unidades vendidas
PRODUCT_B = "a1ffee0000000002"  # beleza_saude, 1 unidade
PRODUCT_C = "c3c3c3c300000003"  # categoria sem tradução
PRODUCT_D = "d4d4d4d400000004"  # sem categoria
PRODUCT_CANCELED = "e5e5e5e500000005"  # só aparece em pedido cancelado: nunca deve aparecer
PRODUCT_UNSOLD = "f6f6f6f600000006"  # nunca vendido

# Dataset (valores usados nas asserções dos testes):
#   o1 entregue no prazo   | A 100 (frete 10, S1) + B 50 (frete 5, S1) | 1 review, nota 5 (pedido de 2 itens)
#   o2 entregue ATRASADO   | A 120 (frete 20, S2)                      | nota 1
#   o3 CANCELADO           | A 100 + CANCELED 999                      | nota 5 (ignorada)
#   o4 entregue no prazo   | C 30 (frete 3, S2)                        | sem review
#   o5 enviado, não entregue | D 20 (frete 2, S1) + A 80 (frete 8, S1) | nota 3
#   o6 entregue ATRASADO   | A 90 + A 90 (frete 9, S1)                 | 2 reviews, notas 4 e 2 (média 3)
_SCHEMA = """
CREATE TABLE products (
    product_id VARCHAR, product_category_name VARCHAR, product_name_length BIGINT,
    product_description_length BIGINT, product_photos_qty BIGINT, product_weight_g DOUBLE,
    product_length_cm DOUBLE, product_height_cm DOUBLE, product_width_cm DOUBLE);
CREATE TABLE product_category_name_translation (product_category_name VARCHAR, product_category_name_english VARCHAR);
CREATE TABLE sellers (seller_id VARCHAR, seller_zip_code_prefix VARCHAR, seller_city VARCHAR, seller_state VARCHAR);
CREATE TABLE orders (
    order_id VARCHAR, customer_id VARCHAR, order_status VARCHAR, order_purchase_timestamp TIMESTAMP,
    order_approved_at TIMESTAMP, order_delivered_carrier_date TIMESTAMP, order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP);
CREATE TABLE order_items (
    order_id VARCHAR, order_item_id BIGINT, product_id VARCHAR, seller_id VARCHAR,
    shipping_limit_date TIMESTAMP, price DOUBLE, freight_value DOUBLE);
CREATE TABLE order_reviews (review_id VARCHAR, order_id VARCHAR, review_score BIGINT);
"""

_PRODUCTS = [
    (PRODUCT_A, "beleza_saude", 40, 300, 3, 500.0, 20.0, 10.0, 15.0),
    (PRODUCT_B, "beleza_saude", 35, 200, 2, 250.0, 10.0, 5.0, 8.0),
    (PRODUCT_C, "categoria_sem_traducao", None, None, None, None, None, None, None),
    (PRODUCT_D, None, 20, 100, 1, 100.0, 5.0, 5.0, 5.0),
    (PRODUCT_CANCELED, "beleza_saude", 30, 150, 1, 300.0, 6.0, 6.0, 6.0),
    (PRODUCT_UNSOLD, "esporte_lazer", 30, 150, 1, 300.0, 6.0, 6.0, 6.0),
]
_TRANSLATIONS = [("beleza_saude", "health_beauty"), ("esporte_lazer", "sports_leisure")]
_SELLERS = [("s1_seller", "01000", "sao paulo", "SP"), ("s2_seller", "20000", "rio", "RJ")]
# (order_id, status, compra, entregue ao cliente, estimativa)
_ORDERS = [
    ("o1", "delivered", "2018-01-10", "2018-01-15", "2018-01-20"),
    ("o2", "delivered", "2018-02-05", "2018-02-12", "2018-02-10"),
    ("o3", "canceled", "2018-02-07", None, "2018-02-20"),
    ("o4", "delivered", "2018-03-01", "2018-03-09", "2018-03-10"),
    ("o5", "shipped", "2018-03-15", None, "2018-03-25"),
    ("o6", "delivered", "2018-03-20", "2018-03-23", "2018-03-22"),
]
# (order_id, item, product, seller, price, frete)
_ITEMS = [
    ("o1", 1, PRODUCT_A, "s1_seller", 100.0, 10.0),
    ("o1", 2, PRODUCT_B, "s1_seller", 50.0, 5.0),
    ("o2", 1, PRODUCT_A, "s2_seller", 120.0, 20.0),
    ("o3", 1, PRODUCT_A, "s1_seller", 100.0, 10.0),
    ("o3", 2, PRODUCT_CANCELED, "s1_seller", 999.0, 99.0),
    ("o4", 1, PRODUCT_C, "s2_seller", 30.0, 3.0),
    ("o5", 1, PRODUCT_D, "s1_seller", 20.0, 2.0),
    ("o5", 2, PRODUCT_A, "s1_seller", 80.0, 8.0),
    ("o6", 1, PRODUCT_A, "s1_seller", 90.0, 9.0),
    ("o6", 2, PRODUCT_A, "s1_seller", 90.0, 9.0),
]
_REVIEWS = [("r1", "o1", 5), ("r2", "o2", 1), ("r3", "o3", 5), ("r5", "o5", 3), ("r6a", "o6", 4), ("r6b", "o6", 2)]


def _ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def build_olist_fixture(path: Path) -> None:
    with duckdb.connect(str(path)) as con:
        con.execute(_SCHEMA)
        con.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", _PRODUCTS)
        con.executemany("INSERT INTO product_category_name_translation VALUES (?, ?)", _TRANSLATIONS)
        con.executemany("INSERT INTO sellers VALUES (?, ?, ?, ?)", _SELLERS)
        con.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
            [(oid, f"c-{oid}", status, _ts(buy), _ts(done), _ts(est)) for oid, status, buy, done, est in _ORDERS],
        )
        con.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?, NULL, ?, ?)", _ITEMS)
        con.executemany("INSERT INTO order_reviews VALUES (?, ?, ?)", _REVIEWS)


@pytest.fixture
def analytics_engine(client, tmp_path):
    path = tmp_path / "olist_test.duckdb"
    build_olist_fixture(path)
    engine = SQLEngine(path, timeout_s=5, max_concurrent=2)
    engine.open()
    client.app.dependency_overrides[get_sql_engine] = lambda: engine
    yield engine
    engine.close()
