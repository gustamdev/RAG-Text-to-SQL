"""Orquestra a gravação de uma linha do golden dataset: busca o contexto da sessão na
memória (services/memory.py) e grava no Mongo (database/golden_data.py)."""

from pymongo.asynchronous.database import AsyncDatabase

from app.database import golden_data
from app.services.memory import MemoryService


async def record_feedback(
    db: AsyncDatabase,
    memory: MemoryService,
    *,
    session_id: str,
    question: str,
    answer: str,
    is_approved: bool,
) -> str:
    context = await memory.context_for_golden_record(session_id)
    return await golden_data.registrar(
        db,
        conversation_id=session_id,
        question=question,
        answer=answer,
        context=context,
        is_approved=is_approved,
    )
