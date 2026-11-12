"""Regressão do golden dataset: roda cada pergunta do golden_data contra o agente de
verdade, pela API real (ver docs/MAPA_DA_API.md; POST /chat/questions + GET .../events),
e imprime a resposta antiga ao lado da nova. Serve para julgar visualmente se o agente
melhorou, não como um "juiz" automático de qualidade (ainda não existe um avaliador).

Precisa de Mongo real rodando, do motor DuckDB já construído (`data/olist.duckdb`) e de uma
OPENAI_API_KEY válida — chama o pipeline inteiro, com LLMs de verdade. Por isso é marcado
`integration` e NÃO roda no `uv run pytest` padrão (ver addopts em pyproject.toml). Para
rodar:

    uv run pytest tests/test_golden_regression.py -m integration -s

(`-s` é necessário: sem ele, o pytest esconde os prints mesmo quando o teste passa.)

Limitação conhecida: cada linha do golden_data é reperguntada numa sessão NOVA, sem o
contexto de conversa que existia na hora do feedback original (esse contexto não sobrevive
a um restart do processo, e hoje não há como "semear" uma sessão de fora). Para perguntas
que dependiam de turnos anteriores (ex.: "e sobre esse cliente?"), a pergunta sozinha pode
não ter informação suficiente — isso é mostrado junto com o CONTEXTO NA ÉPOCA, para quem for
ler a comparação não confundir "piorou" com "faltou contexto que não dá pra repetir".
"""

import json

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.api.deps import get_chat_limiter, require_admin
from app.config import settings
from app.database import golden_data

pytestmark = pytest.mark.integration

REQUEST_TIMEOUT_S = 120
CONTEXT_PREVIEW_CHARS = 300


def _fetch_golden_rows() -> list[dict]:
    with MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000) as client:
        db = client[settings.MONGO_DB_NAME]
        return list(db[golden_data.TABELA].find({}).sort("chat_range_id", 1))


def _ask(client: TestClient, question: str) -> dict:
    """POST + GET, exatamente como documentado em docs/MAPA_DA_API.md. Devolve o evento
    final inteiro (não só `answer`): o `node` diz se foi uma resposta de verdade ou o
    fallback genérico de erro (`node == "error"`, ver services/agent_runner.py)."""
    asked = client.post("/api/v1/chat/questions", json={"question": question})
    asked.raise_for_status()
    question_id = asked.json()["question_id"]

    stream = client.get(f"/api/v1/chat/questions/{question_id}/events")
    stream.raise_for_status()
    events = [json.loads(line[len("data: ") :]) for line in stream.text.splitlines() if line.startswith("data: ")]
    return events[-1]


def test_golden_dataset_regression():
    rows = _fetch_golden_rows()
    if not rows:
        pytest.skip("golden_data está vazia — nada para comparar.")

    from app.main import app

    # O chat agora exige administrador e tem limite por usuário: aqui o teste fala como um admin
    # de mentira e sem limite de perguntas (é uma rodada deliberada, com a chave da OpenAI).
    class _Unlimited:
        def allow(self, _key: str) -> bool:
            return True

    app.dependency_overrides[require_admin] = lambda: {"_id": "golden-regression", "role": "admin"}
    app.dependency_overrides[get_chat_limiter] = lambda: _Unlimited()

    with TestClient(app) as client:
        failures = []
        for row in rows:
            event = _ask(client, row["question"])
            new_answer = event.get("answer") or ""
            crashed = event.get("node") == "error"

            selo = "👍" if row["is_approved"] else "👎"
            context = row.get("context", "") or ""
            if len(context) > CONTEXT_PREVIEW_CHARS:
                context = context[:CONTEXT_PREVIEW_CHARS] + "…"

            print(f"\n{'=' * 100}")
            print(f"[{row['chat_range_id']}] {selo} aprovação original")
            print(f"PERGUNTA: {row['question']}")
            print(f"CONTEXTO NA ÉPOCA: {context or '(nenhum)'}")
            print(f"--- RESPOSTA ORIGINAL (reprovada/aprovada pelo usuário) ---\n{row['answer']}")
            print(f"--- RESPOSTA NOVA (agora){' — ERRO, não foi uma resposta de verdade' if crashed else ''} ---")
            print(new_answer or "(vazia)")

            if crashed or not new_answer.strip():
                failures.append(row["question"])

    app.dependency_overrides.clear()
    assert not failures, f"O agente não conseguiu responder de verdade para: {failures!r}"
