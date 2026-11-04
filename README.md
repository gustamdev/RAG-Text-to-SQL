# RAG - Text to SQL

Agente que responde perguntas em linguagem natural sobre dados de vendas, gerando e executando SQL de forma segura. Usa como base o dataset público de e-commerce da Olist (2017/2018).

**Stack:** Python · FastAPI · LangChain · LangGraph · LangSmith · OpenAI · DuckDB · MongoDB · sqlglot · Pydantic · React · TypeScript · Vite

> Projeto de estudo, feito para praticar engenharia de IA e backend com LLM.

## O que o projeto mostra

- **Agente orquestrado com LangGraph:** `StateGraph` com roteamento condicional entre triagem, seleção de schema, geração, validação e execução do SQL.
- **Intent classification:** um nó de triagem com few-shot separa conversa comum de perguntas que precisam consultar o banco.
- **Schema linking:** o *prompt optimizer* reescreve a pergunta e escolhe só as tabelas e colunas relevantes, reduzindo o contexto enviado ao modelo.
- **Catálogo de metadados gerado por LLM:** cada tabela é amostrada e descrita (colunas, significado, relacionamentos) uma única vez, com cache em memória.
- **Structured output com Pydantic:** toda etapa do LLM tem contrato de entrada e saída validado, com pós-processamento determinístico.
- **Guardrails de SQL:** a consulta é analisada pela AST do `sqlglot` e só passa se for leitura (`SELECT`/`WITH`), com tabelas do catálogo, sem funções perigosas e com `LIMIT` garantido.
- **Defesa em profundidade:** além do validador, o DuckDB roda somente leitura, sem acesso externo, com timeout e limite de concorrência.
- **Self-correction loop:** quando o SQL é rejeitado ou falha, o erro volta para o modelo como feedback, com orçamento de 3 tentativas.
- **Grounding e prompt injection:** a resposta final usa só as linhas retornadas, e os prompts têm hierarquia de instruções contra injeção pela pergunta ou pelos dados.
- **Roteamento de modelos por tarefa:** `gpt-4.1` para SQL, `gpt-4.1-mini` para saída estruturada e um modelo menor para texto, equilibrando custo e qualidade.
- **Memória de sessão:** padrão *buffer + summary*, com as últimas interações na íntegra e um resumo consolidado a cada N turnos.
- **Streaming com SSE:** cada nó do grafo emite um evento, e o frontend mostra o progresso em tempo real.
- **Human feedback e golden dataset:** o 👍/👎 do usuário vira um registro no MongoDB para avaliação e testes de regressão.
- **Observabilidade com LangSmith:** tracing de chains, nós do grafo e etapas marcadas com `@traceable` (validação, execução e catálogo).

## Fluxo do agente

```
START ─► triage ──chat──► chat ──────────────────────────────► END
           │
         data
           ▼
        optimize ◄───────────────── retry_optimize ───┐
           ▼                                          │
      generate_sql ◄──────── retry ──────┐            │
           ▼                             │            │
      validate_sql ──ok──► execute_sql ──┘ (falhou)   │
           │  └── unanswerable ───────────────────────┘
           ▼
        finalize ──► END
```

## Arquitetura

- **MongoDB** é a fonte dos dados: no primeiro start, o backend baixa os CSVs do Olist e popula as coleções.
- **DuckDB** guarda um snapshot analítico e somente leitura dessas coleções, onde o SQL gerado é executado.
- **FastAPI** expõe a API em `/api/v1`, com backend em camadas (rotas, schemas, services, database).
- **React** consome a API com `fetch` e lê a stream SSE de eventos do agente.

## API

| Método | Rota | O que faz |
|---|---|---|
| `GET` | `/api/v1/health` | Status da aplicação e do MongoDB |
| `POST` | `/api/v1/chat/questions` | Envia a pergunta e devolve `question_id` e `session_id` (202) |
| `GET` | `/api/v1/chat/questions/{id}/events` | Stream SSE com um evento por nó do grafo até a resposta final |
| `POST` | `/api/v1/chat/questions/{id}/feedback` | Grava o feedback (thumbs up/down) no golden dataset |

Detalhes de cada rota em [backend/docs/MAPA_DA_API.md](backend/docs/MAPA_DA_API.md).

## Como rodar

Requisitos: Python 3.13, [uv](https://docs.astral.sh/uv/), Node.js, Docker e uma chave da OpenAI.

```bash
git clone https://github.com/gustamdev/RAG-Text-to-SQL.git
cd RAG-Text-to-SQL

# Backend (sobe o MongoDB via docker compose, faz o seed e gera o snapshot DuckDB)
cd backend
cp .env.example .env   # preencha OPENAI_API_KEY
uv sync
uv run python run.py

# Frontend (em outro terminal)
cd frontend
npm ci
npm run dev
```

A API fica em `http://localhost:8000` (Swagger em `/docs`) e o frontend em `http://localhost:5173`.

Para ligar o tracing, preencha `LANGSMITH_TRACING=true` e `LANGSMITH_API_KEY` no `.env`.

## Testes

```bash
cd backend
uv run pytest
```

São 71 testes que rodam sem OpenAI e sem banco real (LLMs e serviços simulados). Os testes de integração ficam marcados com `integration` e não rodam por padrão.

## Estrutura

```
backend/
  src/app/
    agent_graph.py   grafo do agente (LangGraph)
    prompts.py       templates, schemas de entrada/saída e validador de SQL
    llm_models.py    perfis de modelo por tarefa
    api/routes/      rotas de health e chat
    services/        catálogo, memória, execução do agente e das consultas
    database/        MongoDB, seed, snapshot DuckDB e golden dataset
  tests/             testes unitários (pytest)
frontend/            chat em React com streaming dos eventos
docker-compose.yml   MongoDB local
```

## Dados e licenças

Dados: [Olist](https://www.olist.com), publicados no [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) sob a licença [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). O recorte usado aqui vem de [Olist-E-Commerce-Public-Dataset-2017-2018](https://github.com/gustamdev/Olist-E-Commerce-Public-Dataset-2017-2018).
