import asyncio

from app.database import golden_data
from app.services.golden_dataset import record_feedback
from app.services.memory import MemoryService
from tests.test_golden_data import FakeDatabase
from tests.test_memory import FakeSummarizer


def run(coro):
    return asyncio.run(coro)


def test_record_feedback_persists_question_answer_and_session_context():
    db = FakeDatabase()
    memory = MemoryService(FakeSummarizer(responses=["x"]), max_turns=10, context_max_tokens=10_000, ttl_s=3600, max_sessions=100)

    async def scenario():
        # A pergunta já foi registrada na memória pelo AgentRunner antes do usuário poder
        # dar o feedback (record_turn roda no finally de _run, antes do streaming acabar).
        await memory.record_turn("sessao-1", "quem mais comprou?", "o cliente X", tool_note="tabelas: orders")
        return await record_feedback(
            db, memory, session_id="sessao-1", question="quem mais comprou?", answer="o cliente X", is_approved=True
        )

    chat_range_id = run(scenario())

    assert chat_range_id
    doc = db.collections[golden_data.TABELA].docs[0]
    assert doc["chat_range_id"] == chat_range_id
    assert doc["conversation_id"] == "sessao-1"
    assert doc["question"] == "quem mais comprou?"
    assert doc["answer"] == "o cliente X"
    assert doc["is_approved"] is True
    assert "quem mais comprou?" in doc["context"]  # sem resumo ainda: cai nos turnos pendentes


def test_record_feedback_thumbs_down_is_stored_as_false():
    db = FakeDatabase()
    memory = MemoryService(FakeSummarizer(responses=["x"]), max_turns=10, context_max_tokens=10_000, ttl_s=3600, max_sessions=100)

    chat_range_id = run(
        record_feedback(
            db, memory, session_id="sessao-2", question="q", answer="resposta errada", is_approved=False
        )
    )

    doc = db.collections[golden_data.TABELA].docs[0]
    assert doc["chat_range_id"] == chat_range_id
    assert doc["is_approved"] is False
