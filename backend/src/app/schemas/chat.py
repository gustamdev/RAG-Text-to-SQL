from pydantic import BaseModel, Field

MAX_QUESTION_CHARS = 2000
# Vira chave de dict direto em services/memory.py: mesma lógica defensiva de MAX_QUESTION_CHARS.
MAX_SESSION_ID_CHARS = 128


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    session_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_SESSION_ID_CHARS,
        description=(
            "Reenvie o session_id da resposta anterior para dar continuidade à conversa; omita para começar uma nova."
        ),
    )


class AskResponse(BaseModel):
    question_id: str
    session_id: str


class AgentEvent(BaseModel):
    """Um passo do grafo (app/agent_graph.py), serializado como uma linha SSE.

    `node` é o nome do nó que acabou de rodar; `done`/`answer` só vêm preenchidos no
    evento final (nó "chat" ou "finalize"), que fecha o streaming.
    """

    node: str
    label: str
    detail: str | None = None
    done: bool = False
    answer: str | None = None


class ThreadSummary(BaseModel):
    session_id: str
    title: str
    updated_at: str


class ThreadMessage(BaseModel):
    question_id: str
    question: str
    answer: str
    steps: list[AgentEvent] = []


class ThreadDetail(ThreadSummary):
    messages: list[ThreadMessage]
