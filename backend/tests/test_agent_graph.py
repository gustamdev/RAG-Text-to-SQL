import asyncio

import duckdb
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from app.agent_graph import answer_question, build_agent_graph
from app.database.sql_engine import SQLEngine
from app.prompts import ColumnDescription, TableDescriptionOutput, TableMetadata
from app.services.catalog import CatalogService
from app.services.query_runner import QueryRunner


def _column(name: str) -> ColumnDescription:
    return ColumnDescription(
        column_name=name, data_type="string", description="d", semantic_role="r", confidence="high"
    )


CATALOG = [
    TableMetadata(
        schema_name="olist",
        table_name="orders",
        description=TableDescriptionOutput(
            table_name="orders",
            description="Pedidos",
            business_domain="vendas",
            information_type="transação",
            granularity="um por pedido",
            analytical_use_cases=["contagem de pedidos"],
        ),
        columns=[_column("order_id"), _column("order_status")],
    )
]

OPTIMIZED = {
    "original_question": "Quantos pedidos existem?",
    "interpreted_intent": "contar pedidos",
    "relevant_tables": [{"table_name": "orders", "justification": "contém os pedidos"}],
    "relevant_columns": [{"table_name": "orders", "column_name": "order_id", "meaning": "id", "usage": "aggregate"}],
    "filters": [],
    "metrics_and_aggregations": ["contagem"],
    "grouping_and_ordering": [],
    "query_plan": ["contar linhas de orders"],
    "ambiguities": [],
    "missing_information": [],
    "sql_context": "contar pedidos",
}


class StubCatalog(CatalogService):
    """Catálogo fixo: a geração via LLM já é testada em test_catalog.py."""

    def __init__(self, catalog: list[TableMetadata] | None = None):
        self._catalog = CATALOG if catalog is None else catalog

    async def get(self, table_names=None):
        return self._catalog


class ScriptedLLM(FakeListChatModel):
    """Saída estruturada vinda de uma fila por schema; `with_structured_output` ignora o
    prompt e só consome a próxima resposta da fila (ou repete a última, se só restar uma)."""

    queues: dict = {}
    prompts_seen: list = []  # str(prompt renderizado) por chamada, para checar o que foi enviado

    async def ainvoke(self, input, config=None, **kwargs):
        # chat_node/answer_chain chamam o modelo direto (texto livre, sem with_structured_output
        # abaixo) — captura aqui pega esse caminho; o de saída estruturada é capturado em respond().
        self.prompts_seen.append(str(input))
        return await super().ainvoke(input, config, **kwargs)

    def with_structured_output(self, schema, **kw):
        name = schema.__name__

        def respond(_input):
            self.prompts_seen.append(str(_input))
            queue = self.queues[name]
            value = queue.pop(0) if len(queue) > 1 else queue[0]
            return schema.model_validate(value)

        return RunnableLambda(respond)


@pytest.fixture
def engine(tmp_path):
    path = tmp_path / "t.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("CREATE TABLE orders AS SELECT i AS order_id, 'ok' AS order_status FROM range(3) t(i)")
    engine = SQLEngine(path, timeout_s=5, max_concurrent=2)
    engine.open()
    yield engine
    engine.close()


@pytest.fixture
def runner(engine):
    return QueryRunner(engine, ttl_s=60, max_results=10)


def run(llm: ScriptedLLM, runner: QueryRunner, question: str, catalog: list[TableMetadata] | None = None):
    graph = build_agent_graph(
        StubCatalog(catalog),
        runner,
        triage_llm=llm,
        chat_llm=llm,
        optimizer_llm=llm,
        sql_llm=llm,
        answer_llm=llm,
    )
    return asyncio.run(answer_question(graph, question))


def test_chat_question_never_touches_sql(runner):
    llm = ScriptedLLM(responses=["Posso ajudar com perguntas sobre os dados de vendas."])
    llm.queues = {"TriageOutput": [{"intent": "chat", "reason": "saudação"}]}

    state = run(llm, runner, "Oi, o que você faz?")

    assert state["intent"] == "chat"
    assert "agent_output" not in state
    assert state["answer"] == "Posso ajudar com perguntas sobre os dados de vendas."


def test_data_question_succeeds_on_first_try(runner):
    llm = ScriptedLLM(responses=["Existem 3 pedidos registrados."])
    llm.queues = {
        "TriageOutput": [{"intent": "data", "reason": "pede uma contagem"}],
        "PromptOptimizerOutput": [OPTIMIZED],
        "SQLAgentOutput": [{"status": "ok", "sql": "select count(*) as total from orders", "explanation": "e"}],
    }

    state = run(llm, runner, "Quantos pedidos existem?")

    assert state["intent"] == "data"
    assert state["query_result"].status == "succeeded"
    assert state["query_result"].rows == [[3]]
    assert state["attempts"] == 0
    assert state["answer"] == "Existem 3 pedidos registrados."


def test_unsafe_sql_is_retried_then_recovers(runner):
    # 1ª tentativa: usa uma tabela fora das que o optimizer escolheu -> o nó de validação do
    # agente rejeita antes de chegar ao motor. 2ª tentativa: consulta válida.
    llm = ScriptedLLM(responses=["Existem 3 pedidos registrados."])
    llm.queues = {
        "TriageOutput": [{"intent": "data", "reason": "pede uma contagem"}],
        "PromptOptimizerOutput": [OPTIMIZED],
        "SQLAgentOutput": [
            {"status": "ok", "sql": "delete from orders", "explanation": "e1"},
            {"status": "ok", "sql": "select count(*) as total from orders", "explanation": "e2"},
        ],
    }

    state = run(llm, runner, "Quantos pedidos existem?")

    assert state["attempts"] == 1
    assert state["query_result"].status == "succeeded"
    assert "agent_output" in state and state["agent_output"].sql == "select count(*) as total from orders"


def test_sql_error_is_retried_then_recovers(runner):
    # 1ª tentativa: coluna que não existe -> o motor (DuckDB) recusa. 2ª: consulta válida.
    llm = ScriptedLLM(responses=["Existem 3 pedidos registrados."])
    llm.queues = {
        "TriageOutput": [{"intent": "data", "reason": "pede uma contagem"}],
        "PromptOptimizerOutput": [OPTIMIZED],
        "SQLAgentOutput": [
            {"status": "ok", "sql": "select nao_existe from orders", "explanation": "e1"},
            {"status": "ok", "sql": "select count(*) as total from orders", "explanation": "e2"},
        ],
    }

    state = run(llm, runner, "Quantos pedidos existem?")

    assert state["attempts"] == 1
    assert state["query_result"].status == "succeeded"


def test_exhausting_retries_gives_up_without_crashing(runner):
    bad = {"status": "ok", "sql": "delete from orders", "explanation": "sempre errado"}
    llm = ScriptedLLM(responses=["não usado"])
    llm.queues = {
        "TriageOutput": [{"intent": "data", "reason": "pede uma contagem"}],
        "PromptOptimizerOutput": [OPTIMIZED],
        "SQLAgentOutput": [bad],  # fila com 1 item: repete para as 3 tentativas
    }

    state = run(llm, runner, "Quantos pedidos existem?")

    assert state["attempts"] == 3
    assert "query_result" not in state
    assert "Não consegui concluir a consulta" in state["answer"]


def test_needs_clarification_skips_execution_entirely(runner):
    llm = ScriptedLLM(responses=["não usado"])
    llm.queues = {
        "TriageOutput": [{"intent": "data", "reason": "ambígua"}],
        "PromptOptimizerOutput": [OPTIMIZED],
        "SQLAgentOutput": [
            {
                "status": "needs_clarification",
                "explanation": "'melhores' é ambíguo.",
                "clarification_questions": ["Melhores por receita ou por número de pedidos?"],
            }
        ],
    }

    state = run(llm, runner, "Quais são os melhores clientes?")

    assert "query_result" not in state
    assert "Melhores por receita" in state["answer"]


def test_empty_catalog_short_circuits_before_optimizer(runner):
    llm = ScriptedLLM(responses=["não usado"])
    llm.queues = {"TriageOutput": [{"intent": "data", "reason": "pede dados"}]}

    state = run(llm, runner, "Quantos pedidos existem?", catalog=[])

    assert "optimized" not in state
    assert "agent_output" not in state or state["agent_output"].status == "unanswerable"
    assert "catálogo de tabelas" in state["answer"]


def _build_graph(llm, runner, catalog=None):
    return build_agent_graph(
        StubCatalog(catalog), runner, triage_llm=llm, chat_llm=llm, optimizer_llm=llm, sql_llm=llm, answer_llm=llm
    )


def test_chat_node_forwards_conversation_context_to_the_prompt(runner):
    llm = ScriptedLLM(responses=["ok"])
    llm.queues = {"TriageOutput": [{"intent": "chat", "reason": "conversa"}]}
    graph = _build_graph(llm, runner)

    asyncio.run(
        graph.ainvoke(
            {"question": "e sobre isso?", "attempts": 0, "conversation_context": "falamos sobre pedidos cancelados"}
        )
    )

    assert any("falamos sobre pedidos cancelados" in p for p in llm.prompts_seen)


def test_optimize_node_forwards_conversation_context_to_prompt_optimizer(runner):
    llm = ScriptedLLM(responses=["ok"])
    llm.queues = {
        "TriageOutput": [{"intent": "data", "reason": "pede dados"}],
        "PromptOptimizerOutput": [OPTIMIZED],
        "SQLAgentOutput": [{"status": "ok", "sql": "select count(*) as total from orders", "explanation": "e"}],
    }
    graph = _build_graph(llm, runner)

    asyncio.run(
        graph.ainvoke(
            {
                "question": "Quantos pedidos existem?",
                "attempts": 0,
                "conversation_context": "contexto da sessão anterior",
            }
        )
    )

    assert any("contexto da sessão anterior" in p for p in llm.prompts_seen)


def test_missing_conversation_context_key_does_not_break_the_graph(runner):
    # Retrocompatibilidade: estado inicial sem a chave (como todos os testes acima fazem
    # via `run()`/`answer_question`) continua funcionando normalmente.
    llm = ScriptedLLM(responses=["Oi!"])
    llm.queues = {"TriageOutput": [{"intent": "chat", "reason": "saudação"}]}

    state = run(llm, runner, "oi")

    assert state["answer"] == "Oi!"


def test_unanswerable_sql_retries_via_optimizer_before_giving_up(runner):
    # 1ª seleção do optimizer só pega "orders" -> SQL_AGENT fica sem a tabela que precisa e
    # devolve unanswerable. Isso deve voltar pro optimize (não pro generate_sql direto), que
    # reconsidera e amplia a seleção; só então o SQL_AGENT consegue responder.
    narrow = {**OPTIMIZED, "relevant_tables": [{"table_name": "orders", "justification": "j"}]}
    wide = {
        **OPTIMIZED,
        "relevant_tables": [
            {"table_name": "orders", "justification": "j"},
            {"table_name": "customers", "justification": "estava faltando"},
        ],
    }
    catalog_with_customers = [
        *CATALOG,
        TableMetadata(
            schema_name="olist",
            table_name="customers",
            description=TableDescriptionOutput(
                table_name="customers",
                description="Clientes",
                business_domain="vendas",
                information_type="cadastro",
                granularity="um por cliente",
                analytical_use_cases=["dados do cliente"],
            ),
            columns=[_column("customer_id")],
        ),
    ]
    llm = ScriptedLLM(responses=["Existem 3 pedidos."])
    llm.queues = {
        "TriageOutput": [{"intent": "data", "reason": "pede dados"}],
        "PromptOptimizerOutput": [narrow, wide],
        "SQLAgentOutput": [
            {"status": "unanswerable", "explanation": "falta a tabela customers na seleção"},
            {"status": "ok", "sql": "select count(*) as total from orders", "explanation": "e"},
        ],
    }

    state = run(llm, runner, "Quantos pedidos existem, com dados do cliente?", catalog=catalog_with_customers)

    assert state["attempts"] == 1
    assert [t.table_name for t in state["optimized"].relevant_tables] == ["orders", "customers"]
    assert state["query_result"].status == "succeeded"
    # O feedback foi consumido pelo optimizer; não deve "vazar" pro generate_sql como se
    # fosse erro de validação de SQL.
    assert state.get("last_error") is None


def test_needs_clarification_does_not_retry_via_optimizer(runner):
    # Diferente de "unanswerable": pergunta ambígua não se resolve reconsiderando tabelas.
    llm = ScriptedLLM(responses=["não usado"])
    llm.queues = {
        "TriageOutput": [{"intent": "data", "reason": "ambígua"}],
        "PromptOptimizerOutput": [OPTIMIZED],
        "SQLAgentOutput": [
            {
                "status": "needs_clarification",
                "explanation": "'melhores' é ambíguo.",
                "clarification_questions": ["Por receita ou por quantidade?"],
            }
        ],
    }

    state = run(llm, runner, "Quais os melhores clientes?")

    assert state["attempts"] == 0  # nenhuma retentativa foi contabilizada
    assert "query_result" not in state
    assert "Por receita ou por quantidade?" in state["answer"]
