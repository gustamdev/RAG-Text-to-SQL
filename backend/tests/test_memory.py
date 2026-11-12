import asyncio

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from app.services.memory import MemoryService


class FakeSummarizer(FakeListChatModel):
    """Fake do LLM de resumo: conta tentativas, guarda o texto do prompt renderizado (para
    checar se `previous_summary` chegou), pode falhar N vezes antes de suceder e pode
    travar num `asyncio.Event` para simular uma consolidação lenta."""

    calls: int = 0
    successes: int = 0
    prompts_seen: list = []
    fail_next: int = 0
    gate: object | None = None  # asyncio.Event; se setado, respond() espera antes de seguir

    def with_structured_output(self, schema, **kw):
        async def respond(prompt_value):
            self.calls += 1
            self.prompts_seen.append(str(prompt_value))
            if self.gate is not None:
                await self.gate.wait()
            if self.fail_next > 0:
                self.fail_next -= 1
                raise RuntimeError("falha simulada do sumarizador")
            self.successes += 1
            return schema.model_validate({"summary": f"resumo #{self.successes}"})

        return RunnableLambda(respond)

    def get_num_tokens(self, text: str) -> int:
        # Determinístico e independente de tiktoken/transformers: 1 "token" por palavra.
        return len(text.split())


def run(coro):
    return asyncio.run(coro)


def make_service(llm=None, *, max_turns=10, context_max_tokens=10_000, ttl_s=3600, max_sessions=100):
    return MemoryService(
        llm or FakeSummarizer(responses=["x"]),
        max_turns=max_turns,
        context_max_tokens=context_max_tokens,
        ttl_s=ttl_s,
        max_sessions=max_sessions,
    )


def test_new_session_has_no_context_until_first_turn():
    service = make_service()

    async def scenario():
        before = await service.render_context("s1")
        await service.record_turn("s1", "oi", "olá")
        after = await service.render_context("s1")
        return before, after

    before, after = run(scenario())

    assert before == "sem contexto anterior"
    assert "oi" in after and "olá" in after


def test_pending_holds_last_n_unconsolidated_turns_in_order():
    llm = FakeSummarizer(responses=["x"])
    service = make_service(llm, max_turns=3)

    async def scenario():
        for i in range(2):  # 2 turnos, abaixo do limite de 3 — não deve consolidar
            await service.record_turn("s1", f"pergunta {i}", f"resposta {i}")

    run(scenario())

    session = service._sessions["s1"]
    assert [t.question for t in session.pending] == ["pergunta 0", "pergunta 1"]
    assert llm.calls == 0


def test_consolidation_fires_exactly_at_nth_turn_not_before_or_after():
    llm = FakeSummarizer(responses=["x"])
    service = make_service(llm, max_turns=3)

    async def record(i):
        await service.record_turn("s1", f"pergunta {i}", f"resposta {i}")

    run(record(0))
    run(record(1))
    assert llm.calls == 0  # 2 de 3: ainda não

    run(record(2))  # 3º turno completa o lote
    session = service._sessions["s1"]
    assert llm.calls == 1
    assert len(session.pending) == 0
    assert session.summary == "resumo #1"

    run(record(3))  # 4º turno: começa um novo lote, não dispara de novo
    assert llm.calls == 1
    assert [t.question for t in service._sessions["s1"].pending] == ["pergunta 3"]


def test_second_batch_incorporates_previous_summary():
    llm = FakeSummarizer(responses=["x"])
    service = make_service(llm, max_turns=2)

    async def scenario():
        await service.record_turn("s1", "p0", "r0")
        await service.record_turn("s1", "p1", "r1")  # consolida -> summary = "resumo #1"
        await service.record_turn("s1", "p2", "r2")
        await service.record_turn("s1", "p3", "r3")  # consolida de novo

    run(scenario())

    assert llm.calls == 2
    # O segundo prompt renderizado precisa conter o resumo da primeira leva, não "sem resumo anterior".
    assert "resumo #1" in llm.prompts_seen[1]
    assert "sem resumo anterior" not in llm.prompts_seen[1]


def test_pending_preserved_while_consolidation_is_in_flight():
    gate = asyncio.Event()
    llm = FakeSummarizer(responses=["x"], gate=gate)
    service = make_service(llm, max_turns=2)

    async def scenario():
        await service.record_turn("s1", "p0", "r0")
        task = asyncio.create_task(service.record_turn("s1", "p1", "r1"))  # completa o lote, trava no gate
        await asyncio.sleep(0.05)
        # Ainda travado: nada foi perdido nem limpo prematuramente.
        pending_during = list(service._sessions["s1"].pending)
        gate.set()
        await task
        return pending_during

    pending_during = run(scenario())

    assert [t.question for t in pending_during] == ["p0", "p1"]
    assert service._sessions["s1"].pending == service._sessions["s1"].pending  # ainda existe, sem lançar
    assert service._sessions["s1"].summary == "resumo #1"


def test_consolidation_failure_preserves_turns_and_recovers_on_retry():
    llm = FakeSummarizer(responses=["x"], fail_next=1)
    service = make_service(llm, max_turns=2)

    async def scenario():
        await service.record_turn("s1", "p0", "r0")
        await service.record_turn("s1", "p1", "r1")  # completa o lote, sumarizador falha

    run(scenario())
    session = service._sessions["s1"]
    assert session.summary == ""  # não mudou
    assert [t.question for t in session.pending] == ["p0", "p1"]  # nada se perdeu
    assert llm.calls == 1

    run(service.record_turn("s1", "p2", "r2"))  # dispara nova tentativa, agora sucede

    assert llm.calls == 2
    assert service._sessions["s1"].summary == "resumo #1"
    assert [t.question for t in service._sessions["s1"].pending] == ["p2"]  # não duplicou p0/p1


def test_sessions_are_isolated():
    service = make_service(max_turns=5)

    async def scenario():
        await service.record_turn("a", "pergunta da sessão A", "resposta A")
        await service.record_turn("b", "pergunta da sessão B", "resposta B")
        return await service.render_context("a"), await service.render_context("b")

    context_a, context_b = run(scenario())

    assert "sessão A" in context_a and "sessão B" not in context_a
    assert "sessão B" in context_b and "sessão A" not in context_b


def _extract_questions(prompt_text: str) -> list[str]:
    import re

    return re.findall(r'"question":\s*"(p\d+)"', prompt_text)


def test_concurrent_record_turn_same_session_loses_nothing_and_never_double_consolidates():
    llm = FakeSummarizer(responses=["x"])
    service = make_service(llm, max_turns=3)
    total = 9  # 3 lotes exatos de 3

    async def scenario():
        await asyncio.gather(*(service.record_turn("s1", f"p{i}", f"r{i}") for i in range(total)))

    run(scenario())

    session = service._sessions["s1"]
    assert llm.calls == 3  # exatamente 3 lotes, nunca mais nem menos
    assert list(session.pending) == [] and session.overflow == []  # 9 é múltiplo exato de 3: nada sobra

    batches = [frozenset(_extract_questions(p)) for p in llm.prompts_seen]
    all_questions = {f"p{i}" for i in range(total)}
    assert all(len(b) == 3 for b in batches)  # cada lote tem exatamente max_turns perguntas
    assert len(set(batches)) == 3  # nenhum lote repetido (sem dupla consolidação)
    assert set().union(*batches) == all_questions  # todas as 9 perguntas foram consolidadas, nenhuma perdida
    assert sum(len(b) for b in batches) == len(all_questions)  # lotes disjuntos: nada duplicado entre lotes


def test_render_context_respects_token_budget_dropping_oldest_whole():
    llm = FakeSummarizer(responses=["x"])
    service = make_service(llm, max_turns=10, context_max_tokens=6)

    async def scenario():
        await service.record_turn("s1", "pergunta antiga " * 10, "resposta antiga " * 10)  # bem maior que o orçamento
        await service.record_turn("s1", "oi", "tudo bem")  # pequeno, cabe fácil
        return await service.render_context("s1")

    context = run(scenario())

    assert "antiga" not in context  # turno antigo não truncado no meio: fica de fora inteiro
    assert "tudo bem" in context
    assert llm.get_num_tokens(context) <= service.context_max_tokens


def test_no_duplicate_consolidation_without_a_new_full_batch():
    llm = FakeSummarizer(responses=["x"])
    service = make_service(llm, max_turns=3)

    async def scenario():
        await service.record_turn("s1", "p0", "r0")
        await service.record_turn("s1", "p1", "r1")
        await service.record_turn("s1", "p2", "r2")  # consolida
        await service.render_context("s1")
        await service.render_context("s1")

    run(scenario())

    assert llm.calls == 1


def test_single_turn_exceeding_budget_is_truncated_not_dropped():
    llm = FakeSummarizer(responses=["x"])
    service = make_service(llm, max_turns=10, context_max_tokens=5)

    async def scenario():
        await service.record_turn("s1", "pergunta " * 50, "resposta " * 50)
        return await service.render_context("s1")

    context = run(scenario())

    assert context  # não lança, não fica vazio
    assert "truncado" in context
    assert llm.get_num_tokens(context) <= service.context_max_tokens + 5  # marcador soma poucos tokens extra
    assert not context.rstrip(")").endswith(("pergunta", "resposta"))  # não cortou no meio da palavra


def test_render_context_failure_in_agent_runner_degrades_gracefully():
    # services/agent_runner.py trata falha de render_context separadamente — aqui só
    # confirmamos que record_turn nunca lança mesmo se chamado para uma sessão nova.
    service = make_service()

    async def scenario():
        await service.record_turn("nunca-visitada-antes", "p", "r")

    run(scenario())  # não deve lançar


def test_context_for_golden_record_uses_summary_when_available():
    llm = FakeSummarizer(responses=["x"])
    service = make_service(llm, max_turns=2)

    async def scenario():
        await service.record_turn("s1", "p0", "r0")
        await service.record_turn("s1", "p1", "r1")  # consolida -> summary = "resumo #1"
        return await service.context_for_golden_record("s1")

    context = run(scenario())

    assert context == "resumo #1"


def test_context_for_golden_record_falls_back_to_pending_turns_without_summary():
    service = make_service(max_turns=10)

    async def scenario():
        await service.record_turn("s1", "qual o cliente que mais comprou?", "o cliente X")
        return await service.context_for_golden_record("s1")

    context = run(scenario())

    assert "qual o cliente que mais comprou?" in context
    assert "o cliente X" in context


def test_context_for_golden_record_on_untouched_session_says_so():
    service = make_service()

    context = run(service.context_for_golden_record("nunca-visitada"))

    assert context == "sem contexto disponível"
