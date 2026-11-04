"""Repositório da coleção `golden_data`: pares pergunta/resposta aprovados ou reprovados
pelo usuário (thumbs up/down), para alimentar testes de regressão e medir melhora/piora do
modelo no futuro. Cresce com o uso da aplicação — não é recriada pelo seed do Olist.

Documento:
    chat_range_id: str    — UUID v7: ordenável pelo horário de criação (os 48 bits mais
                             altos são um timestamp em ms), mas ainda um UUID de verdade —
                             sem round-trip extra ao Mongo para gerar (nada de contador
                             incrementado à parte, que precisaria de uma segunda escrita).
    conversation_id: str  — session_id da conversa (services/memory.py)
    question: str
    answer: str
    context: str          — resumo consolidado da sessão, ou, sem resumo ainda, os turnos
                             pendentes que seriam usados para produzir um (ver
                             MemoryService.context_for_golden_record)
    is_approved: bool      — true = thumbs up, false = thumbs down
    created_at: datetime
"""

from datetime import UTC, datetime

import uuid_utils
from pymongo.asynchronous.database import AsyncDatabase

TABELA = "golden_data"


async def registrar(
    db: AsyncDatabase, *, conversation_id: str, question: str, answer: str, context: str, is_approved: bool
) -> str:
    """Grava uma linha no golden dataset. Devolve o `chat_range_id` gerado."""
    chat_range_id = str(uuid_utils.uuid7())
    await db[TABELA].insert_one(
        {
            "chat_range_id": chat_range_id,
            "conversation_id": conversation_id,
            "question": question,
            "answer": answer,
            "context": context,
            "is_approved": is_approved,
            "created_at": datetime.now(UTC),
        }
    )
    return chat_range_id
