"""Memória de sessão do agente: histórico recente + resumo consolidado, por `session_id`.

Mesmíssimo padrão já usado 3x no projeto (QueryRunner, AgentRunner, CatalogService): dict em
memória do processo, sem armazenamento externo novo. Não sobrevive a um restart do processo
nem é compartilhada entre workers do uvicorn (`--workers > 1` quebraria o isolamento entre
sessões) — mesma limitação já aceita nos outros três serviços.

Decisão de não usar o checkpointer do LangGraph (`MemorySaver`): ele persiste o `AgentState`
inteiro por `thread_id`, incluindo campos pesados e transitórios de um turno só (agent_output,
query_result, attempts) — granularidade errada para "resumir após N turnos com uma tool
própria". A política abaixo (deque + resumo + consolidação) teria que ser escrita por fora de
qualquer forma, então fica mais simples não envolver o checkpointer.

Padrão "buffer + summary": as últimas N interações ficam verbatim (`pending`); ao completar N
não consolidadas, `resumir_contexto` (SUMMARIZE_CONTEXT em prompts.py) condensa o lote num
resumo que é SOBRESCRITO (variável própria — não um índice reaproveitado dentro do array, que
misturaria dois tipos de dado na mesma estrutura). O histórico recente entra no contexto desde
a 1ª pergunta da sessão; o gatilho de N só controla quando o resumo é atualizado.
"""

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langsmith import traceable

from app.prompts import SUMMARIZE_CONTEXT, SummarizedTurn, SummarizeContextInput

logger = logging.getLogger(__name__)

# Cabe no texto corrido do contexto, mas corta antes de estourar o orçamento de qualquer jeito.
MAX_TRUNCATE_ATTEMPTS = 5


@dataclass
class SessionTurn:
    question: str
    answer: str
    # Nota curta sobre dados/ferramentas usados (ex.: "tabelas: orders, order_items"; "12
    # linha(s)") — nunca SQL ou linhas cruas. Ver agent_runner.py, que extrai isso dos
    # eventos já truncados que _describe() produz, sem lógica nova de extração.
    tool_note: str | None = None


@dataclass
class SessionMemory:
    pending: deque[SessionTurn]
    summary: str = ""
    # Interações que chegaram com `pending` já cheia e a consolidação ainda não liberou
    # espaço (por exemplo, por falha de uma tentativa anterior). Nunca se perdem nem são
    # descartadas pelo maxlen de `pending`: só entram em `pending` depois de confirmado que
    # há espaço (consolidação bem-sucedida), preservando a ordem de chegada.
    overflow: list[SessionTurn] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used_at: float = field(default_factory=time.monotonic)


def _truncate_to_budget(text: str, budget_tokens: int, cost: Callable[[str], int]) -> str:
    """Corta `text` para caber em `budget_tokens`, sem quebrar palavra nem sequência
    multibyte (fatiar `str` do Python é seguro por codepoint), com marcador explícito."""
    marker = " (…truncado por limite de tokens)"
    if budget_tokens <= 0:
        return marker.strip()

    # Chute inicial proporcional (chars por token ~ len(text)/cost(text)), depois ajusta
    # em poucos passos — mais barato que testar cost() caractere por caractere.
    ratio = len(text) / max(cost(text), 1)
    n = max(1, int(budget_tokens * ratio * 0.9))
    for _ in range(MAX_TRUNCATE_ATTEMPTS):
        candidate = text[:n].rsplit(" ", 1)[0] + marker
        if cost(candidate) <= budget_tokens or n <= 1:
            return candidate
        n = max(1, n - max(1, n // 4))
    return marker.strip()


class MemoryService:
    def __init__(
        self, llm: BaseChatModel, *, max_turns: int, context_max_tokens: int, ttl_s: float, max_sessions: int
    ):
        self.llm = llm
        self.max_turns = max_turns
        self.context_max_tokens = context_max_tokens
        self.ttl_s = ttl_s
        self.max_sessions = max_sessions
        self._sessions: dict[str, SessionMemory] = {}

    def _get_or_create(self, session_id: str) -> SessionMemory:
        # Síncrono e sem lock de propósito: dict é criado atomicamente sob o event loop
        # cooperativo (sem `await` no meio), então duas chamadas concorrentes para o mesmo
        # session_id novo não criam duas SessionMemory — a segunda só sobrescreveria com
        # outra instância vazia, nunca corrompe nada em uso.
        self._evict()
        session = self._sessions.get(session_id)
        if session is None:
            session = SessionMemory(pending=deque(maxlen=self.max_turns))
            self._sessions[session_id] = session
        session.last_used_at = time.monotonic()
        return session

    async def render_context(self, session_id: str) -> str:
        """Monta o texto de `conversation_context`: resumo + turnos recentes, sob o
        orçamento de tokens. Chamado antes do grafo rodar (ver agent_runner.py)."""
        session = self._get_or_create(session_id)
        async with session.lock:
            summary, recent = session.summary, [*session.pending, *session.overflow]
        return self._assemble(summary, recent)

    async def context_for_golden_record(self, session_id: str) -> str:
        """Para database/golden_data.py: o resumo consolidado, se existir; senão, os turnos
        ainda pendentes (crus) — são os dados que *seriam* usados para produzir um resumo."""
        session = self._get_or_create(session_id)
        async with session.lock:
            if session.summary:
                return session.summary
            recent = [*session.pending, *session.overflow]
        if not recent:
            return "sem contexto disponível"
        return "\n\n".join(f"[pergunta]: {t.question}\n[resposta]: {t.answer}" for t in recent)

    async def record_turn(self, session_id: str, question: str, answer: str, tool_note: str | None = None) -> None:
        """Grava a interação depois da resposta pronta; dispara a consolidação se isso
        completar um lote de `max_turns` pendentes. Chamado depois do grafo responder."""
        session = self._get_or_create(session_id)
        turn = SessionTurn(question=question, answer=answer, tool_note=tool_note)
        async with session.lock:
            session.overflow.append(turn)
            await self._drain(session)
            session.last_used_at = time.monotonic()

    async def _drain(self, session: SessionMemory) -> None:
        """Pré-condição: chamado com `session.lock` já adquirido.

        Move `overflow` -> `pending`, consolidando sempre que `pending` completa
        `max_turns`. Garante que `pending` nunca recebe um append quando já está no limite
        sem ter sido resumida antes — então o `deque(maxlen=max_turns)` nunca precisa
        descartar nada por conta própria; ele é uma rede de segurança, não o mecanismo.
        """
        while session.overflow:
            if len(session.pending) >= self.max_turns:
                if not await self._consolidate(session):
                    return  # falhou: overflow preserva tudo, próxima chamada tenta de novo
            session.pending.append(session.overflow.pop(0))
            if len(session.pending) >= self.max_turns:
                await self._consolidate(session)  # gatilho estrito: exatamente ao completar o N-ésimo

    @traceable(
        run_type="chain",
        name="memory_consolidate",
        process_inputs=lambda inputs: {"turns": len(inputs["session"].pending)},
    )
    async def _consolidate(self, session: SessionMemory) -> bool:
        batch = list(session.pending)
        try:
            output = await SUMMARIZE_CONTEXT.chain(self.llm).ainvoke(
                SummarizeContextInput(
                    previous_summary=session.summary or None,
                    turns=[SummarizedTurn(question=t.question, answer=t.answer, tool_note=t.tool_note) for t in batch],
                )
            )
        except Exception:
            # Loga sem expor conteúdo da conversa; interações pendentes continuam intactas
            # para a próxima tentativa (próximo record_turn tenta de novo).
            logger.exception("Falha ao consolidar memória (%d interação(ões) pendente(s)).", len(batch))
            return False
        session.summary = output.summary  # só muda em caso de sucesso
        session.pending.clear()  # só limpa em caso de sucesso — batch intacto até aqui
        return True

    def _assemble(self, summary: str, recent: list[SessionTurn]) -> str:
        cost = self.llm.get_num_tokens  # reaproveita tiktoken via ChatOpenAI; sem dependência nova
        budget = self.context_max_tokens
        used = 0

        rendered_summary = ""
        if summary:
            rendered_summary = summary if cost(summary) <= budget else _truncate_to_budget(summary, budget, cost)
            used = cost(rendered_summary)

        # Do mais recente para o mais antigo: se o orçamento não cabe tudo, descarta o que
        # é mais antigo primeiro, nunca o que acabou de ser perguntado.
        blocks: list[str] = []
        for turn in reversed(recent):
            remaining = budget - used
            if remaining <= 0:
                break
            block = f"[pergunta]: {turn.question}\n[resposta]: {turn.answer}"
            if turn.tool_note:
                block += f"\n[nota]: {turn.tool_note}"
            block_cost = cost(block)
            if block_cost <= remaining:
                blocks.append(block)
                used += block_cost
                continue
            if not blocks:
                # É o turno mais recente (nenhum outro entrou ainda) e, sozinho, não cabe no
                # orçamento: trunca com segurança em vez de mandar o contexto vazio.
                blocks.append(_truncate_to_budget(block, remaining, cost))
                used += remaining
            # Turnos mais antigos que não cabem ficam de fora por completo — truncar um
            # turno antigo no meio seria pior que simplesmente não incluí-lo.
            break
        blocks.reverse()

        sections = ([f"Resumo da conversa até aqui:\n{rendered_summary}"] if rendered_summary else []) + blocks
        return "\n\n".join(sections) if sections else "sem contexto anterior"

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_used_at > self.ttl_s]
        overflow = sorted(self._sessions, key=lambda sid: self._sessions[sid].last_used_at)[
            : max(0, len(self._sessions) - self.max_sessions)
        ]
        for sid in {*expired, *overflow}:
            self._sessions.pop(sid, None)
