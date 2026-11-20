import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_agent_runner, get_chat_limiter, get_db, require_admin
from app.core.errors import NotFound, TooManyRequests
from app.core.rate_limit import SlidingWindowLimiter
from app.core.timeutil import iso
from app.database.repos.chat_threads import ChatThreadsRepo
from app.schemas.chat import AskRequest, AskResponse, ThreadDetail, ThreadSummary
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services.agent_runner import AgentRunner
from app.services.golden_dataset import record_feedback

logger = logging.getLogger(__name__)

# O chat gasta tokens de LLM e roda SQL gerado: só administradores.
router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_admin)])

QUESTION_NOT_FOUND = "Pergunta não encontrada."
THREAD_NOT_FOUND = "Conversa não encontrada."


@router.post("/questions", response_model=AskResponse, status_code=status.HTTP_202_ACCEPTED)
async def ask_question(
    payload: AskRequest,
    user: dict = Depends(require_admin),
    runner: AgentRunner = Depends(get_agent_runner),
    limiter: SlidingWindowLimiter = Depends(get_chat_limiter),
) -> AskResponse:
    if not limiter.allow(user["_id"]):
        raise TooManyRequests("Limite de perguntas atingido. Aguarde alguns minutos e tente de novo.")
    question_id, session_id = runner.ask(payload.question, payload.session_id, user_id=user["_id"])
    return AskResponse(question_id=question_id, session_id=session_id)


@router.get("/questions/{question_id}/events")
async def stream_question_events(
    question_id: str,
    user: dict = Depends(require_admin),
    runner: AgentRunner = Depends(get_agent_runner),
):
    if not runner.owns(question_id, user["_id"]):
        raise NotFound(QUESTION_NOT_FOUND)

    async def event_source():
        async for event in runner.events(question_id):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        # Sem buffer de proxy (nginx) e sem cache: cada evento precisa chegar assim que sai.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/questions/{question_id}/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    question_id: str,
    payload: FeedbackRequest,
    user: dict = Depends(require_admin),
    db: AsyncDatabase = Depends(get_db),
    runner: AgentRunner = Depends(get_agent_runner),
) -> FeedbackResponse:
    """Thumbs up/down da última resposta: grava no golden dataset (database/golden_data.py)."""
    if not runner.owns(question_id, user["_id"]):
        raise NotFound(QUESTION_NOT_FOUND)
    chat_range_id = await record_feedback(
        db,
        runner.memory,
        session_id=runner.session_key(user["_id"], payload.session_id),
        question=payload.question,
        answer=payload.answer,
        is_approved=payload.is_approved,
    )
    logger.info(
        "Feedback registrado (question_id=%s, chat_range_id=%s, aprovado=%s)",
        question_id,
        chat_range_id,
        payload.is_approved,
    )
    return FeedbackResponse(chat_range_id=chat_range_id)


@router.get("/threads", response_model=list[ThreadSummary])
async def list_threads(user: dict = Depends(require_admin), db: AsyncDatabase = Depends(get_db)):
    rows = await ChatThreadsRepo(db).list(user["_id"])
    return [ThreadSummary(session_id=r["session_id"], title=r["title"], updated_at=iso(r["updated_at"])) for r in rows]


@router.get("/threads/{session_id}", response_model=ThreadDetail)
async def get_thread(session_id: str, user: dict = Depends(require_admin), db: AsyncDatabase = Depends(get_db)):
    thread = await ChatThreadsRepo(db).get(user["_id"], session_id)
    if thread is None:
        raise NotFound(THREAD_NOT_FOUND)
    messages = [{k: m[k] for k in ("question_id", "question", "answer", "steps")} for m in thread["messages"]]
    return ThreadDetail(
        session_id=thread["session_id"],
        title=thread["title"],
        updated_at=iso(thread["updated_at"]),
        messages=messages,
    )


@router.delete("/threads/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    session_id: str,
    user: dict = Depends(require_admin),
    db: AsyncDatabase = Depends(get_db),
    runner: AgentRunner = Depends(get_agent_runner),
) -> None:
    if not await ChatThreadsRepo(db).delete(user["_id"], session_id):
        raise NotFound(THREAD_NOT_FOUND)
    runner.memory.forget(runner.session_key(user["_id"], session_id))
