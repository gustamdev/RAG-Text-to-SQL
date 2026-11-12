"""Roda o grafo do agente (agent_graph.py) em segundo plano e expõe o progresso nó a nó.

Par POST (`ask`) / GET (`events`), no mesmo molde do QueryRunner: o POST devolve um id na
hora e dispara a execução; o GET consome os eventos dessa execução, em tempo real, até o
evento final (que já traz a resposta). Pensado para virar um endpoint `text/event-stream`.
"""

import asyncio
import logging
import time
import uuid

from langgraph.graph.state import CompiledStateGraph

from app.prompts import SQLAgentOutput
from app.schemas.chat import AgentEvent
from app.schemas.query import QueryResult
from app.services.memory import MemoryService

logger = logging.getLogger(__name__)

MAX_DETAIL_CHARS = 400

_NODE_LABELS = {
    "triage": "Entendendo a pergunta",
    "chat": "Respondendo",
    "optimize": "Selecionando tabelas e colunas",
    "generate_sql": "Gerando a consulta SQL",
    "validate_sql": "Validando a consulta",
    "execute_sql": "Executando no banco",
    "finalize": "Montando a resposta",
}

# Nós em que o grafo termina: o update desse nó já é o evento final do streaming.
_TERMINAL_NODES = frozenset({"chat", "finalize"})


def _describe(node: str, update: dict | None) -> AgentEvent:
    """Traduz o dict que o LangGraph devolve por nó (ver `StateGraph.astream`) num evento de
    UI. `update` vem `None` quando o nó não alterou o estado (ex.: validação sem erro)."""
    update = update or {}
    label = _NODE_LABELS.get(node, node)
    detail: str | None = None

    if node == "triage":
        detail = f"intenção: {update.get('intent')}"
    elif node == "optimize":
        optimized = update.get("optimized")
        if optimized is None:
            detail = "catálogo de tabelas indisponível"
        else:
            tables = ", ".join(t.table_name for t in optimized.relevant_tables)
            detail = f"tabelas: {tables}" if tables else "nenhuma tabela relevante identificada"
    elif node == "generate_sql":
        output: SQLAgentOutput | None = update.get("agent_output")
        detail = output.sql if output and output.status == "ok" else (output.explanation if output else None)
    elif node == "validate_sql":
        error = update.get("last_error")
        detail = f"rejeitada pela checagem do agente: {error}" if error else "consulta aprovada"
    elif node == "execute_sql":
        result: QueryResult | None = update.get("query_result")
        if result is None:
            detail = None
        elif result.status == "succeeded":
            detail = f"{result.row_count} linha(s) retornada(s)"
        else:
            detail = f"{result.status}: {result.error}"

    if detail and len(detail) > MAX_DETAIL_CHARS:
        detail = detail[:MAX_DETAIL_CHARS] + "…"

    if node in _TERMINAL_NODES:
        answer = update.get("answer", "")
        return AgentEvent(node=node, label=label, detail=answer, done=True, answer=answer)
    return AgentEvent(node=node, label=label, detail=detail)


class AgentRunner:
    def __init__(self, graph: CompiledStateGraph, memory: MemoryService, *, ttl_s: float, max_results: int):
        self.graph = graph
        self.memory = memory
        self.ttl_s = ttl_s
        self.max_results = max_results
        # Cada execução tem seu histórico (para quem conectar atrasado) e uma fila para quem
        # já está conectado receber os eventos em tempo real.
        self._history: dict[str, list[AgentEvent]] = {}
        self._queues: dict[str, asyncio.Queue[AgentEvent | None]] = {}
        self._stored_at: dict[str, float] = {}
        # Dono (id do usuário) de cada execução: o GET de eventos e o feedback só servem a ele.
        self._owners: dict[str, str | None] = {}
        self._tasks: set[asyncio.Task] = set()

    @staticmethod
    def session_key(user_id: str | None, session_id: str) -> str:
        """Chave da memória: a sessão pertence a quem a criou, então um admin não lê a de outro mesmo
        que descubra o `session_id` dela."""
        return f"{user_id}:{session_id}" if user_id else session_id

    def ask(self, question: str, session_id: str | None = None, user_id: str | None = None) -> tuple[str, str]:
        """Devolve (question_id, session_id). Sem session_id, gera um novo — quem reenviar
        esse id na próxima pergunta ganha continuidade; quem ignorar, continua funcionando
        igual a antes (cada pergunta numa sessão isolada, sem memória). `user_id` registra o
        dono da execução (ver `owns`)."""
        self._evict()
        session_id = session_id or uuid.uuid4().hex
        question_id = uuid.uuid4().hex
        self._history[question_id] = []
        self._queues[question_id] = asyncio.Queue()
        self._stored_at[question_id] = time.monotonic()
        self._owners[question_id] = user_id

        task = asyncio.create_task(self._run(question, question_id, self.session_key(user_id, session_id)))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return question_id, session_id

    def exists(self, question_id: str) -> bool:
        return question_id in self._history

    def owns(self, question_id: str, user_id: str) -> bool:
        """True só se a execução existe e foi iniciada por `user_id`. Quem chama responde 404 nos
        dois casos de False, para não revelar que o id existe para outro usuário."""
        return question_id in self._history and self._owners.get(question_id) == user_id

    async def events(self, question_id: str):
        """Repete o histórico (quem conectar atrasado não perde passos) e segue ao vivo."""
        if question_id not in self._history:
            raise KeyError(question_id)
        for event in list(self._history[question_id]):
            yield event
            if event.done:
                return

        queue = self._queues[question_id]
        while True:
            event = await queue.get()
            if event is None:  # sentinela: a execução já tinha terminado antes do for acima
                return
            yield event
            if event.done:
                return

    async def _run(self, question: str, question_id: str, session_id: str) -> None:
        # run_name + metadata: no LangSmith, cada pergunta vira um trace próprio, com esse
        # question_id — é o que liga um erro na tela ("Ocorreu um erro...") ao traceback real.
        config = {
            "run_name": "agent_graph",
            "tags": ["chat"],
            "metadata": {"question_id": question_id, "session_id": session_id},
        }
        answer: str | None = None
        tool_notes: dict[str, str] = {}
        try:
            context = await self.memory.render_context(session_id)
        except Exception:
            # Memória nunca pode impedir a pergunta de ser respondida: segue sem contexto.
            logger.exception("Falha ao montar contexto de memória da sessão %s; seguindo sem contexto.", session_id)
            context = None
        try:
            async for update in self.graph.astream(
                {"question": question, "attempts": 0, "conversation_context": context}, config, stream_mode="updates"
            ):
                ((node, value),) = update.items()
                event = _describe(node, value)
                if node == "optimize" and event.detail:
                    tool_notes["tabelas"] = event.detail
                elif node == "execute_sql" and event.detail:
                    tool_notes["consulta"] = event.detail
                self._history[question_id].append(event)
                self._queues[question_id].put_nowait(event)
                if event.done:
                    answer = event.answer
                    return
        except Exception:
            logger.exception("Falha ao executar o grafo para %s", question_id)
            event = AgentEvent(
                node="error", label="Erro inesperado", done=True, answer="Ocorreu um erro ao processar a pergunta."
            )
            self._history[question_id].append(event)
            self._queues[question_id].put_nowait(event)
        finally:
            if answer is not None:
                # Resposta já entregue via SSE antes daqui (o evento terminal foi enfileirado
                # logo acima); gravar a memória não atrasa o streaming, só prepara a próxima
                # pergunta da mesma sessão. Erro aqui não derruba a resposta já dada.
                tool_note = "; ".join(f"{k}: {v}" for k, v in tool_notes.items()) or None
                try:
                    await self.memory.record_turn(session_id, question, answer, tool_note=tool_note)
                except Exception:
                    logger.exception("Falha ao gravar memória da sessão %s (resposta já entregue).", session_id)
            self._queues[question_id].put_nowait(None)

    def _evict(self) -> None:
        now = time.monotonic()
        expired = [qid for qid, stored_at in self._stored_at.items() if now - stored_at > self.ttl_s]
        overflow = sorted(self._stored_at, key=self._stored_at.get)[: max(0, len(self._stored_at) - self.max_results)]
        for qid in {*expired, *overflow}:
            self._history.pop(qid, None)
            self._queues.pop(qid, None)
            self._stored_at.pop(qid, None)
            self._owners.pop(qid, None)
