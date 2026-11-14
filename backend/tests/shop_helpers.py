"""Apoio dos testes da loja (E2-E4): banco mongomock, produtos/CEPs de teste e troca de cliente logado."""

import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.api.deps import get_app_db
from app.api.shop_deps import get_current_customer

V1 = "/api/v1"


class Shop:
    def __init__(self, client):
        self.client, self.db = client, AsyncMongoMockClient()["shop_test"]
        self.current: dict | None = None
        client.app.dependency_overrides[get_app_db] = lambda: self.db
        client.app.dependency_overrides[get_current_customer] = self._customer

    def _customer(self) -> dict:
        assert self.current is not None
        return self.current

    def login(self, customer_id: str) -> None:
        self.current = {"_id": customer_id}

    def run(self, coro):
        return asyncio.run(coro)

    def product(self, product_id: str, **over) -> dict:
        doc = {
            "product_id": product_id, "category": "cama_mesa_banho", "category_label": "Cama mesa banho",
            "title": f"Cama mesa banho · Modelo {product_id[:4].upper()}", "price_cents": 1000, "stock": 5,
            "weight_g": 1000.0, "length_cm": 10.0, "height_cm": 5.0, "width_cm": 8.0, "photos_qty": 2,
            "review_count": 0, "units_sold": 0, "avg_rating": None, "rating_distribution": {},
        }  # fmt: skip
        doc.update(over)
        self.run(self.db["shop_products"].insert_one(dict(doc)))
        return doc

    def set_product(self, product_id: str, **fields) -> None:
        self.run(self.db["shop_products"].update_one({"product_id": product_id}, {"$set": fields}))

    def geo(self, prefix: str, lat: float, lng: float) -> None:
        self.run(
            self.db["geolocation"].insert_one(
                {"geolocation_zip_code_prefix": prefix, "geolocation_lat": lat, "geolocation_lng": lng}
            )
        )


@pytest.fixture
def shop(client):
    return Shop(client)
