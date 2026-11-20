import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.database.repos.chat_threads import MAX_MESSAGES, ChatThreadsRepo
from app.services.agent_runner import AgentRunner
from tests.test_agent_runner import FakeMemoryService, _build_echo_graph


def _repo():
    return ChatThreadsRepo(AsyncMongoMockClient()["olist_test"])


def _turn(repo, user, sid, q="oi"):
    return repo.add_turn(user, sid, question_id="q", question=q, answer="a", steps=[])


def test_turns_accumulate_in_one_thread_and_title_is_first_question():
    async def scenario():
        repo = _repo()
        await _turn(repo, "u1", "s1", "primeira")
        await _turn(repo, "u1", "s1", "segunda")
        return await repo.get("u1", "s1"), await repo.list("u1")

    thread, listed = asyncio.run(scenario())
    assert [m["question"] for m in thread["messages"]] == ["primeira", "segunda"]
    assert thread["title"] == "primeira"
    assert len(listed) == 1


def test_threads_are_isolated_per_user_and_deletable():
    async def scenario():
        repo = _repo()
        await _turn(repo, "u1", "s1")
        return (
            await repo.get("u2", "s1"),
            await repo.list("u2"),
            await repo.delete("u2", "s1"),
            await repo.delete("u1", "s1"),
            await repo.get("u1", "s1"),
        )

    other_get, other_list, other_delete, own_delete, after = asyncio.run(scenario())
    assert other_get is None and other_list == [] and other_delete is False
    assert own_delete is True and after is None


def test_messages_are_capped():
    async def scenario():
        repo = _repo()
        for i in range(MAX_MESSAGES + 5):
            await _turn(repo, "u1", "s1", f"q{i}")
        return await repo.get("u1", "s1")

    thread = asyncio.run(scenario())
    assert len(thread["messages"]) == MAX_MESSAGES
    assert thread["messages"][-1]["question"] == f"q{MAX_MESSAGES + 4}"


def test_runner_saves_turn_and_rehydrates_memory_after_restart():
    class Memory(FakeMemoryService):
        def __init__(self):
            super().__init__()
            self.seeded = None

        def has(self, sid):
            return False

        def seed(self, sid, turns):
            self.seeded = (sid, turns)

    async def scenario():
        repo = _repo()
        runner = AgentRunner(_build_echo_graph(), Memory(), ttl_s=60, max_results=10, threads=repo)
        qid, sid = runner.ask("primeira", user_id="u1")
        [e async for e in runner.events(qid)]
        await asyncio.sleep(0.05)  # o salvamento roda no finally, depois do evento final
        saved = await repo.get("u1", sid)

        memory = Memory()  # "restart": memória nova, thread no banco
        runner2 = AgentRunner(_build_echo_graph(), memory, ttl_s=60, max_results=10, threads=repo)
        qid2, _ = runner2.ask("segunda", session_id=sid, user_id="u1")
        [e async for e in runner2.events(qid2)]
        return saved, memory.seeded, sid

    saved, seeded, sid = asyncio.run(scenario())
    assert saved["messages"][0]["question"] == "primeira"
    assert seeded[0] == f"u1:{sid}" and seeded[1][0][0] == "primeira"
