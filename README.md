# Olist Insights

[![CI](https://github.com/gustamdev/RAG-Text-to-SQL/actions/workflows/ci.yml/badge.svg)](https://github.com/gustamdev/RAG-Text-to-SQL/actions/workflows/ci.yml)

Backoffice para analisar produtos do e-commerce brasileiro da Olist, com um **assistente Text-to-SQL** que responde perguntas em linguagem natural gerando e executando SQL de forma segura. O site tem duas áreas:

- **Vitrine pública** (`/`, `/produtos`): catálogo de produtos Olist com busca, filtro por categoria, ordenação e paginação.
- **Backoffice** (`/backoffice`, só administrador): visão geral com KPIs, tabela de produtos com métricas (receita, unidades, nota, % de avaliações ruins, % de entregas atrasadas), detalhe por produto, categorias e o **assistente de dados**.

**Stack:** Python · FastAPI · LangChain · LangGraph · LangSmith · OpenAI · DuckDB · MongoDB · sqlglot · Pydantic · React · TypeScript · Vite · TanStack Query · Tailwind · shadcn/ui · Recharts

> Projeto de portfólio, feito para praticar engenharia de IA e backend com LLM. O dataset Olist não traz nome nem foto de produto: a vitrine usa um rótulo sintético (`categoria · #id`) e um ícone por categoria.

## O que o projeto mostra

- **Agente orquestrado com LangGraph:** `StateGraph` com roteamento condicional entre triagem, seleção de schema, geração, validação e execução do SQL.
- **Intent classification:** um nó de triagem com few-shot separa conversa comum de perguntas que precisam consultar o banco.
- **Schema linking:** o *prompt optimizer* reescreve a pergunta e escolhe só as tabelas e colunas relevantes, reduzindo o contexto enviado ao modelo.
- **Catálogo de metadados gerado por LLM:** cada tabela é amostrada e descrita (colunas, significado, relacionamentos) uma única vez, com cache em memória.
- **Structured output com Pydantic:** toda etapa do LLM tem contrato de entrada e saída validado, com pós-processamento determinístico.
- **Guardrails de SQL** (`backend/src/app/sql_guard.py`): a consulta é analisada pela AST do `sqlglot` e só passa se for leitura (`SELECT`/`WITH`), com tabelas do catálogo, sem funções perigosas e com `LIMIT` garantido. Tem suíte de testes com ataques (CTE escondendo tabela, `COPY`, `read_csv`, `PRAGMA`, múltiplas instruções).
- **Defesa em profundidade:** além do validador, o DuckDB roda somente leitura, sem acesso externo, com timeout e limite de concorrência.
- **Self-correction loop:** quando o SQL é rejeitado ou falha, o erro volta para o modelo como feedback, com orçamento de 3 tentativas.
- **Grounding e prompt injection:** a resposta final usa só as linhas retornadas, e os prompts têm hierarquia de instruções contra injeção pela pergunta ou pelos dados.
- **Roteamento de modelos por tarefa:** `gpt-4.1` para SQL, `gpt-4.1-mini` para saída estruturada e um modelo menor para texto.
- **Memória de sessão:** padrão *buffer + summary*, com as últimas interações na íntegra e um resumo consolidado a cada N turnos.
- **Streaming com SSE:** cada nó do grafo emite um evento; o frontend lê o stream com `fetch` (para enviar o JWT) e mostra o progresso em tempo real.
- **Human feedback e golden dataset:** o 👍/👎 vira um registro no MongoDB para avaliação e testes de regressão.
- **Observabilidade com LangSmith:** tracing de chains, nós do grafo e etapas marcadas com `@traceable`.
- **Análises sem LLM:** os endpoints do backoffice usam SQL constante e parametrizado (placeholders, ordenação por allowlist), executado no mesmo motor DuckDB somente leitura.

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

- **MongoDB** é a fonte dos dados: no primeiro start, o backend baixa os CSVs do Olist e popula as coleções. Também guarda os usuários administradores e o golden dataset.
- **DuckDB** guarda um snapshot analítico e somente leitura dessas coleções. É onde rodam tanto o SQL gerado pelo agente quanto as consultas do backoffice.
- **FastAPI** expõe a API em `/api/v1`, em camadas (rotas, schemas, services, database).
- **React** (Vite + React Router + TanStack Query + Tailwind/shadcn) consome a API com `fetch`.

## API

| Método | Rota | Acesso | O que faz |
|---|---|---|---|
| `GET` | `/api/v1/health` | público | Status da aplicação e do MongoDB |
| `GET` | `/api/v1/products`, `/products/{id}`, `/categories` | público | Catálogo paginado, detalhe e categorias |
| `POST` | `/api/v1/auth/login` | público | Login de administrador (JWT) |
| `GET` | `/api/v1/auth/me` | admin | Usuário do token |
| `GET` | `/api/v1/admin/overview`, `/products`, `/products/{id}`, `/categories` | admin | KPIs, produtos e categorias com métricas |
| `POST` | `/api/v1/chat/questions` | admin | Envia a pergunta e devolve `question_id` e `session_id` (202) |
| `GET` | `/api/v1/chat/questions/{id}/events` | admin | Stream SSE com um evento por nó do grafo |
| `POST` | `/api/v1/chat/questions/{id}/feedback` | admin | Grava o feedback (👍/👎) no golden dataset |

Detalhes de cada rota em [backend/docs/MAPA_DA_API.md](backend/docs/MAPA_DA_API.md).

## Como rodar

Requisitos: Python 3.13, [uv](https://docs.astral.sh/uv/), Node.js 22, Docker e uma chave da OpenAI.

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

A API fica em `http://localhost:8000` (Swagger em `/docs`) e o site em `http://localhost:5173`.

Não há cadastro público. Crie o administrador uma vez (a senha é pedida no terminal) e entre em `/backoffice/login`:

```bash
cd backend
uv run python scripts/create_admin.py voce@email.com "Seu Nome"
```

Em produção (`ENV=prod`), defina `JWT_SECRET` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`); sem ele o backend não sobe. Para ligar o tracing, preencha `LANGSMITH_TRACING=true` e `LANGSMITH_API_KEY` no `.env`.

**Tudo em containers** (opcional): `docker compose --profile full up --build` sobe MongoDB, backend e frontend (nginx em `http://localhost:8080`). Precisa do `backend/.env` com `OPENAI_API_KEY` e `JWT_SECRET`.

Por padrão o seed carrega só os pedidos de 2018 (jan–ago). Para carregar todos os anos, defina `SEED_YEAR=` (vazio) e recrie o banco (apague o volume do Mongo e `backend/data/olist.duckdb`).

## Testes e qualidade

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npx oxlint && npx tsc -b && npx vitest run && npm run build
```

Os testes do backend rodam sem OpenAI e sem banco real (LLMs simulados, `mongomock-motor` e DuckDB temporário). Os de integração ficam marcados com `integration` e não rodam por padrão. O CI (GitHub Actions) roda tudo isso a cada push e pull request.

### Avaliação do agente

O golden dataset (👍/👎 dos usuários) alimenta um teste de regressão que repergunta cada item ao agente real e imprime a resposta antiga ao lado da nova:

```bash
cd backend
uv run pytest tests/test_golden_regression.py -m integration -s   # precisa de Mongo, DuckDB e OPENAI_API_KEY
```

Ainda não há um avaliador automático de acurácia; a comparação é visual.

## Decisões e limites

- **sqlglot + DuckDB:** a AST permite validar o SQL antes de executar (não só bloquear palavras), e o DuckDB oferece um motor analítico embutido, somente leitura e com timeout. O validador é a primeira barreira; o motor restrito é a última.
- **MongoDB como fonte e DuckDB como snapshot:** o Mongo guarda os dados brutos, os administradores e o golden dataset; o DuckDB serve a análise. Para um projeto só de análise, ler os CSVs direto no DuckDB seria mais simples.
- **Consultas do backoffice sem LLM:** métricas devem ser determinísticas e baratas; o LLM fica só no assistente.
- **Nota por pedido, não por produto:** a Olist avalia pedidos. Um produto herda a nota dos pedidos em que aparece, e cada pedido conta uma vez por produto.
- **Pedidos cancelados e indisponíveis** ficam fora das métricas.
- **Vitrine sem cache:** cada consulta recalcula as agregações no DuckDB (limitada por IP). Num cenário real, as métricas seriam materializadas no build do snapshot ou cacheadas com TTL.
- **Estado em memória:** memória de sessão, resultados do chat e rate limits vivem no processo. Não sobrevivem a restart nem escalam para vários workers; em produção iriam para Redis.
- **Sem nome nem foto de produto** no dataset: o rótulo é sintético.

## Segurança

- Sem cadastro público; administrador criado por script, com senha em argon2id e tempo de resposta equalizado no login.
- JWT com expiração; o papel é conferido no banco a cada requisição. Rate limit de falhas de login por e-mail e IP.
- Chat e backoffice exigem administrador; cada execução do agente pertence a quem a criou e há limite de perguntas por administrador (custo de LLM).
- SQL do agente: validador por AST, allowlist de tabelas, motor somente leitura sem acesso externo, timeout e limite de linhas. SQL do backoffice: placeholders e ordenação por allowlist.
- Rotas públicas com limite por IP (`PUBLIC_RATE_LIMIT`), CORS restrito a `GET`/`POST` e cabeçalhos de segurança no nginx (CSP, `X-Frame-Options`, `nosniff`).
- Segredos só no `.env` (ignorado pelo git); o `.env.example` não contém valores reais. Com `ENV=prod`, `JWT_SECRET` precisa ter 32+ caracteres.
- A memória de cada conversa é indexada por administrador: outro admin não lê a sessão alheia, mesmo sabendo o `session_id`.

**Limites conhecidos de segurança**

- O MongoDB do compose não tem autenticação e só escuta em `127.0.0.1`; em produção use credenciais e rede privada.
- O JWT fica em `localStorage` (12 h, sem revogação). Em produção o ideal é cookie `HttpOnly` e token curto com refresh.
- Privacidade (LGPD): o catálogo amostra linhas reais e o assistente envia até 50 linhas de resultado à OpenAI; o dataset traz identificadores pseudonimizados (`customer_unique_id`, prefixo de CEP, cidade). Com `LANGSMITH_TRACING=true`, prompts e linhas também vão ao LangSmith. Mantenha o tracing desligado com dados reais, ou aplique mascaramento antes de usar fora de um dataset público.
- Os limites de uso são por processo (em memória); com vários workers, mova-os para Redis.

## Estrutura

```
backend/
  src/app/
    agent_graph.py   grafo do agente (LangGraph)
    prompts.py       templates e contratos de entrada/saída dos prompts
    sql_guard.py     validador de SQL somente leitura (AST do sqlglot)
    llm_models.py    perfis de modelo por tarefa
    api/routes/      health, auth, products (público), backoffice (admin), chat (admin)
    auth/            hash de senha (argon2id) e JWT
    schemas/         contratos Pydantic de cada domínio
    services/        catálogo, memória, agente e análise de produtos
    database/        MongoDB, seed, snapshot DuckDB, analytics (SQL do backoffice), golden dataset
  scripts/           create_admin.py
  tests/             testes (pytest)
frontend/src/
  app/               router, providers e guardas de rota
  pages/             Vitrine/, Backoffice/ e Assistente/ (chat, CSS isolado)
  components/        ui/ (shadcn), layout/, product/, backoffice/, chat/
  services/          http.ts (cliente com JWT), products, backoffice e chat (SSE)
  hooks/             TanStack Query e useChat
docker-compose.yml   MongoDB local (perfil "full": backend e frontend)
```

## Dados e licenças

Código: [MIT](LICENSE). Dados: [Olist](https://www.olist.com), publicados no [Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) sob a licença [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). O recorte usado aqui vem de [Olist-E-Commerce-Public-Dataset-2017-2018](https://github.com/gustamdev/Olist-E-Commerce-Public-Dataset-2017-2018).
