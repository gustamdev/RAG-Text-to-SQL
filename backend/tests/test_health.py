import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.api.deps import get_db


class FakeDatabase:
    def __init__(self, error: Exception | None = None):
        self.error = error

    async def command(self, name: str):
        if self.error:
            raise self.error
        return {"ok": 1}


@pytest.fixture
def client_with_db(app):
    def build(database: FakeDatabase) -> TestClient:
        app.dependency_overrides[get_db] = lambda: database
        return TestClient(app)

    yield build
    app.dependency_overrides.clear()


def test_health_ok_when_database_responds(client_with_db):
    response = client_with_db(FakeDatabase()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_is_down(client_with_db):
    response = client_with_db(FakeDatabase(ServerSelectionTimeoutError("down"))).get("/api/v1/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
