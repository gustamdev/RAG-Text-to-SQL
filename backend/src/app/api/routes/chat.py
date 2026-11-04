import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_agent_runner, get_db
from app.schemas.chat import AskRequest, AskResponse
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.services.agent_runner import AgentRunner
from app.services.golden_dataset import record_feedback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/questions", response_model=AskResponse, status_code=status.HTTP_202_ACCEPTED)
async def ask_question(payload: AskRequest, runner: AgentRunner = Depends(get_agent_runner)) -> AskResponse:
    question_id, session_id = runner.ask(payload.question, payload.session_id)
    return AskResponse(question_id=question_id, session_id=session_id)


@router.get("/questions/{question_id}/events")
async def stream_question_events(question_id: str, runner: AgentRunner = Depends(get_agent_runner)):
    if not runner.exists(question_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pergunta não encontrada.")

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
    db: AsyncDatabase = Depends(get_db),
    runner: AgentRunner = Depends(get_agent_runner),
) -> FeedbackResponse:
    """Thumbs up/down da última resposta: grava no golden dataset (database/golden_data.py)."""
    chat_range_id = await record_feedback(
        db,
        runner.memory,
        session_id=payload.session_id,
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
