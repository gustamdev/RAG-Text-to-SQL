import asyncio
import re

from app.database import golden_data

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}$")


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    async def insert_one(self, document):
        self.docs.append(document)


class FakeDatabase:
    def __init__(self):
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())


def run(coro):
    return asyncio.run(coro)


def test_registrar_inserts_all_fields_with_a_uuid7_chat_range_id():
    db = FakeDatabase()

    chat_range_id = run(
        golden_data.registrar(db, conversation_id="s1", question="q1", answer="a1", context="ctx1", is_approved=True)
    )

    assert UUID_RE.match(chat_range_id)  # UUID v7: o "7" na 3ª posição marca a versão
    docs = db.collections[golden_data.TABELA].docs
    assert docs[0] == {
        "chat_range_id": chat_range_id,
        "conversation_id": "s1",
        "question": "q1",
        "answer": "a1",
        "context": "ctx1",
        "is_approved": True,
        "created_at": docs[0]["created_at"],
    }


def test_chat_range_ids_are_time_ordered_and_distinct():
    db = FakeDatabase()

    first = run(golden_data.registrar(db, conversation_id="a", question="q", answer="a", context="c", is_approved=True))
    second = run(
        golden_data.registrar(db, conversation_id="b", question="q", answer="a", context="c", is_approved=False)
    )

    assert first != second
    assert first < second  # UUID v7 é ordenável pelo horário de criação, sem contador extra


def test_registrar_without_db_counter_round_trip():
    # Diferente do auto-incremento tradicional, não há um "counters" à parte: o id nasce
    # no próprio app (uuid7), então uma única escrita no Mongo basta.
    db = FakeDatabase()

    run(golden_data.registrar(db, conversation_id="a", question="q", answer="a", context="c", is_approved=True))

    assert "counters" not in db.collections
