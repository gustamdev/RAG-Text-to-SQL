"""Chat atrás do admin: 401/403, limite por usuário e isolamento entre administradores."""

import asyncio

import pytest
from langgraph.graph import END, START, StateGraph

from app.api.deps import get_agent_runner, get_db
from app.config import settings
from app.services.agent_runner import AgentRunner
from tests.test_golden_data import FakeDatabase

ASK = "/api/v1/chat/questions"


async def _chat_node(state):
    await asyncio.sleep(0)
    return {"answer": f"eco: {state['question']}"}


class FakeMemory:
    async def render_context(self, session_id):
        return None

    async def record_turn(self, session_id, question, answer, tool_note=None):
        return None

    async def context_for_golden_record(self, session_id):
        return "ctx"


@pytest.fixture
def runner(client, auth_db):
    graph = StateGraph(dict)
    graph.add_node("chat", _chat_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)
    runner = AgentRunner(graph.compile(), FakeMemory(), ttl_s=60, max_results=10)
    client.app.dependency_overrides[get_agent_runner] = lambda: runner
    client.app.dependency_overrides[get_db] = lambda: FakeDatabase()
    return runner


def _feedback_body():
    return {"session_id": "s", "question": "q", "answer": "a", "is_approved": True}


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", ASK), ("GET", f"{ASK}/qualquer/events"), ("POST", f"{ASK}/qualquer/feedback")],
)
def test_chat_requires_token(client, auth_db, runner, method, path):
    res = client.request(method, path, json={"question": "oi"})

    assert res.status_code == 401


@pytest.mark.parametrize("path", [ASK, f"{ASK}/qualquer/events", f"{ASK}/qualquer/feedback"])
def test_chat_rejects_non_admin_with_403(client, auth_db, runner, path):
    headers, _ = auth_db.create_non_admin()

    res = client.request("GET" if path.endswith("events") else "POST", path, json={"question": "oi"}, headers=headers)

    assert res.status_code == 403


def test_admin_can_ask_and_read_own_events(client, auth_db, runner):
    headers, _ = auth_db.create_admin()

    asked = client.post(ASK, json={"question": "Quantos pedidos?"}, headers=headers)
    events = client.get(f"{ASK}/{asked.json()['question_id']}/events", headers=headers)

    assert asked.status_code == 202
    assert events.status_code == 200
    assert '"answer":"eco: Quantos pedidos?"' in events.text


def test_ask_is_rate_limited_per_user(client, auth_db, runner, monkeypatch):
    monkeypatch.setattr(settings, "CHAT_RATE_LIMIT", 2)
    first, _ = auth_db.create_admin(email="a@teste.com")
    second, _ = auth_db.create_admin(email="b@teste.com")

    codes = [client.post(ASK, json={"question": "oi"}, headers=first).status_code for _ in range(3)]
    other = client.post(ASK, json={"question": "oi"}, headers=second)

    assert codes == [202, 202, 429]
    assert other.status_code == 202  # a cota é por admin, não global
    assert client.post(ASK, json={"question": "oi"}, headers=first).json()["detail"].startswith("Limite")


def test_other_admin_gets_404_for_events_and_feedback(client, auth_db, runner):
    owner, _ = auth_db.create_admin(email="dono@teste.com")
    intruder, _ = auth_db.create_admin(email="outro@teste.com")
    question_id = client.post(ASK, json={"question": "segredo"}, headers=owner).json()["question_id"]

    events = client.get(f"{ASK}/{question_id}/events", headers=intruder)
    feedback = client.post(f"{ASK}/{question_id}/feedback", json=_feedback_body(), headers=intruder)

    assert events.status_code == 404
    assert feedback.status_code == 404
    assert events.json() == client.get(f"{ASK}/nao-existe/events", headers=intruder).json()  # não revela o id
    # O dono continua com acesso.
    assert client.get(f"{ASK}/{question_id}/events", headers=owner).status_code == 200
    assert client.post(f"{ASK}/{question_id}/feedback", json=_feedback_body(), headers=owner).status_code == 201


def test_session_key_is_namespaced_by_user():
    from app.services.agent_runner import AgentRunner

    assert AgentRunner.session_key("admin-a", "s1") != AgentRunner.session_key("admin-b", "s1")
    assert AgentRunner.session_key(None, "s1") == "s1"
