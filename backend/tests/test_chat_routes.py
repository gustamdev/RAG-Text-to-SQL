import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph

from app.api.deps import get_agent_runner, get_db
from app.services.agent_runner import AgentRunner
from tests.test_golden_data import FakeDatabase


async def _fake_node(state):
    await asyncio.sleep(0)
    return {"answer": f"eco: {state['question']}"}


def _build_fake_graph():
    """Grafo mínimo de 1 nó: os testes de rota não precisam exercitar agent_graph.py de
    novo (isso já é feito em test_agent_graph.py), só o transporte HTTP/SSE em volta."""
    graph = StateGraph(dict)
    graph.add_node("chat", _fake_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)
    return graph.compile()


@pytest.fixture
def db():
    return FakeDatabase()


@pytest.fixture
def client_with_runner(app, db):
    def build(runner: AgentRunner) -> TestClient:
        app.dependency_overrides[get_agent_runner] = lambda: runner
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    yield build
    app.dependency_overrides.clear()


class FakeMemoryService:
    """No-op: estes testes só exercitam o transporte HTTP/SSE em volta do grafo, a memória
    de sessão em si é testada em test_memory.py."""

    def __init__(self):
        self.recorded: list[tuple[str, str, str]] = []

    async def render_context(self, session_id: str) -> str | None:
        return None

    async def record_turn(self, session_id: str, question: str, answer: str, tool_note: str | None = None) -> None:
        self.recorded.append((session_id, question, answer))

    async def context_for_golden_record(self, session_id: str) -> str:
        return f"contexto de {session_id}"


@pytest.fixture
def memory():
    return FakeMemoryService()


@pytest.fixture
def runner(memory):
    return AgentRunner(_build_fake_graph(), memory, ttl_s=60, max_results=10)


def _parse_sse(body: str) -> list[dict]:
    return [json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")]


def test_ask_returns_a_question_id(client_with_runner, runner):
    response = client_with_runner(runner).post("/api/v1/chat/questions", json={"question": "oi"})

    assert response.status_code == 202
    assert response.json()["question_id"]


def test_ask_without_session_id_returns_a_generated_one(client_with_runner, runner):
    response = client_with_runner(runner).post("/api/v1/chat/questions", json={"question": "oi"})

    assert response.json()["session_id"]


def test_ask_echoes_session_id_when_provided(client_with_runner, runner):
    response = client_with_runner(runner).post(
        "/api/v1/chat/questions", json={"question": "oi", "session_id": "sessao-fixa"}
    )

    assert response.json()["session_id"] == "sessao-fixa"


def test_ask_rejects_empty_question(client_with_runner, runner):
    response = client_with_runner(runner).post("/api/v1/chat/questions", json={"question": ""})

    assert response.status_code == 422


def test_events_stream_ends_with_the_answer(client_with_runner, runner):
    client = client_with_runner(runner)
    question_id = client.post("/api/v1/chat/questions", json={"question": "Quantos pedidos?"}).json()["question_id"]

    response = client.get(f"/api/v1/chat/questions/{question_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert events[-1] == {
        "node": "chat",
        "label": "Respondendo",
        "detail": "eco: Quantos pedidos?",
        "done": True,
        "answer": "eco: Quantos pedidos?",
    }


def test_events_for_unknown_question_is_404(client_with_runner, runner):
    response = client_with_runner(runner).get("/api/v1/chat/questions/nao-existe/events")

    assert response.status_code == 404


def test_feedback_thumbs_up_persists_to_golden_dataset(client_with_runner, runner, db):
    from app.database import golden_data

    response = client_with_runner(runner).post(
        "/api/v1/chat/questions/alguma-pergunta/feedback",
        json={"session_id": "sessao-1", "question": "q", "answer": "a", "is_approved": True},
    )

    assert response.status_code == 201
    assert response.json()["chat_range_id"]
    doc = db.collections[golden_data.TABELA].docs[0]
    assert doc["conversation_id"] == "sessao-1"
    assert doc["is_approved"] is True
    assert doc["context"] == "contexto de sessao-1"  # via FakeMemoryService.context_for_golden_record


def test_feedback_thumbs_down_is_stored_as_false(client_with_runner, runner, db):
    from app.database import golden_data

    client_with_runner(runner).post(
        "/api/v1/chat/questions/alguma-pergunta/feedback",
        json={"session_id": "sessao-2", "question": "q", "answer": "resposta ruim", "is_approved": False},
    )

    assert db.collections[golden_data.TABELA].docs[0]["is_approved"] is False


def test_feedback_rejects_empty_question(client_with_runner, runner):
    response = client_with_runner(runner).post(
        "/api/v1/chat/questions/x/feedback",
        json={"session_id": "s", "question": "", "answer": "a", "is_approved": True},
    )

    assert response.status_code == 422
