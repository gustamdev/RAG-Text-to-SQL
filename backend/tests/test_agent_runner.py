import asyncio

from langgraph.graph import END, START, StateGraph

from app.services.agent_runner import AgentRunner


class FakeMemoryService:
    def __init__(self, *, context: str | None = "sem contexto anterior", record_gate: asyncio.Event | None = None):
        self.context = context
        self.record_gate = record_gate  # se setado, record_turn espera antes de retornar
        self.render_calls: list[str] = []
        self.recorded: list[tuple[str, str, str, str | None]] = []

    async def render_context(self, session_id: str) -> str | None:
        self.render_calls.append(session_id)
        return self.context

    async def record_turn(self, session_id: str, question: str, answer: str, tool_note: str | None = None) -> None:
        if self.record_gate is not None:
            await self.record_gate.wait()
        self.recorded.append((session_id, question, answer, tool_note))


async def _echo_node(state: dict) -> dict:
    return {"answer": f"eco: {state['question']} | ctx={state.get('conversation_context')}"}


def _build_echo_graph():
    graph = StateGraph(dict)
    graph.add_node("chat", _echo_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)
    return graph.compile()


async def _failing_node(_state: dict) -> dict:
    raise RuntimeError("falha simulada no grafo")


def _build_failing_graph():
    graph = StateGraph(dict)
    graph.add_node("chat", _failing_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)
    return graph.compile()


async def _drain(runner: AgentRunner, question_id: str) -> list:
    return [event async for event in runner.events(question_id)]


def test_ask_without_session_id_generates_distinct_sessions():
    memory = FakeMemoryService()
    runner = AgentRunner(_build_echo_graph(), memory, ttl_s=60, max_results=10)

    async def scenario():
        qid1, session_1 = runner.ask("pergunta 1")
        qid2, session_2 = runner.ask("pergunta 2")
        await _drain(runner, qid1)
        await _drain(runner, qid2)
        return session_1, session_2

    session_1, session_2 = asyncio.run(scenario())

    # Chamadas separadas sem session_id: cada uma recebe sua própria sessão.
    assert session_1 != session_2
    assert {r[0] for r in memory.recorded} == {session_1, session_2}  # memória nunca cruzou sessão


def test_ask_with_same_session_id_reuses_it_across_calls():
    memory = FakeMemoryService()
    runner = AgentRunner(_build_echo_graph(), memory, ttl_s=60, max_results=10)

    async def scenario():
        qid1, sid = runner.ask("pergunta 1", "sessao-fixa")
        await _drain(runner, qid1)
        qid2, sid2 = runner.ask("pergunta 2", "sessao-fixa")
        await _drain(runner, qid2)
        return sid, sid2

    sid1, sid2 = asyncio.run(scenario())

    assert sid1 == sid2 == "sessao-fixa"
    # As duas perguntas gravaram memória sob a MESMA sessão, na ordem certa.
    assert [r[0] for r in memory.recorded] == ["sessao-fixa", "sessao-fixa"]
    assert [r[1] for r in memory.recorded] == ["pergunta 1", "pergunta 2"]


def test_conversation_context_from_memory_reaches_the_graph():
    memory = FakeMemoryService(context="resumo: usuário perguntou sobre pedidos antes")
    runner = AgentRunner(_build_echo_graph(), memory, ttl_s=60, max_results=10)

    async def scenario():
        qid, sid = runner.ask("e sobre isso?", "sessao-1")
        events = await _drain(runner, qid)
        return sid, events

    sid, events = asyncio.run(scenario())

    assert memory.render_calls == [sid]
    assert "resumo: usuário perguntou sobre pedidos antes" in events[-1].answer


def test_answer_is_delivered_before_record_turn_completes():
    gate = asyncio.Event()
    memory = FakeMemoryService(record_gate=gate)
    runner = AgentRunner(_build_echo_graph(), memory, ttl_s=60, max_results=10)

    async def scenario():
        qid, _sid = runner.ask("pergunta")
        events = await _drain(runner, qid)  # events() retorna assim que vê done=True
        # Nesse ponto o streaming já terminou; record_turn pode ainda estar travado no gate.
        recorded_before_gate = list(memory.recorded)
        gate.set()
        await asyncio.sleep(0.05)
        return events, recorded_before_gate

    events, recorded_before_gate = asyncio.run(scenario())

    assert events[-1].done is True
    assert recorded_before_gate == []  # resposta já entregue, memória ainda não gravada
    assert len(memory.recorded) == 1  # e depois do gate liberar, grava normalmente


def test_graph_error_never_calls_record_turn():
    memory = FakeMemoryService()
    runner = AgentRunner(_build_failing_graph(), memory, ttl_s=60, max_results=10)

    async def scenario():
        qid, _sid = runner.ask("pergunta")
        return await _drain(runner, qid)

    events = asyncio.run(scenario())

    assert events[-1].node == "error"
    assert memory.recorded == []
