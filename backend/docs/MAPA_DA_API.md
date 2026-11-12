# Mapa da API

Todas as rotas vivem sob o prefixo `/api/v1` (`API_VERSION` em `src/app/main.py`).

| Grupo | Acesso |
|---|---|
| `health`, `auth/login`, `products`, `categories` | público |
| `auth/me`, `admin/*`, `chat/*` | JWT Bearer de **administrador** (`require_admin`: o papel é lido do banco a cada chamada, não do token) |

Não existe cadastro público: o administrador é criado por `scripts/create_admin.py`.

Em desenvolvimento, `/docs` (Swagger) e `/redoc` ficam disponíveis; em produção
(`ENV=prod`), os dois e `/openapi.json` são desligados (`settings.is_prod`).

## Health

### `GET /api/v1/health`

Diz se a aplicação e o banco (MongoDB) estão de pé. Usado por orquestradores/monitoramento,
não pelo frontend.

| | |
|---|---|
| Resposta 200 | `{"status": "ok", "database": "ok"}` |
| Resposta 503 | `{"status": "degraded", "database": "unavailable"}` |

Faz um `ping` no Mongo a cada chamada; não verifica o motor SQL (DuckDB) nem a OpenAI.

---

## Chat — perguntar e acompanhar a resposta

Exige `Authorization: Bearer <token>` de administrador (**401** sem token ou token inválido, **403** se não for admin). Cada pergunta pertence a quem a fez: `GET .../events` e `POST .../feedback` de outra pessoa respondem **404**. O `POST /chat/questions` tem limite por administrador (`CHAT_RATE_LIMIT` perguntas a cada `CHAT_RATE_WINDOW_S` segundos; padrão 20 em 600 s) e responde **429** ao estourar. Como o `EventSource` do navegador não envia cabeçalhos, o frontend lê o stream com `fetch` (`frontend/src/lib/sse.ts`).

O fluxo é sempre em dois passos: **POST** dispara a pergunta e devolve na hora um
`question_id`; **GET** acompanha a execução por streaming (SSE) até a resposta ficar
pronta. Isso existe porque o grafo do agente (`src/app/agent_graph.py`) pode levar alguns
segundos — o POST não trava esperando.

### `POST /api/v1/chat/questions`

Envia uma pergunta e começa a processá-la em segundo plano.

**Corpo da requisição** (`AskRequest`):

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `question` | string | sim | 1 a 2000 caracteres |
| `session_id` | string ou null | não | reenvie o da resposta anterior para dar continuidade à conversa; omita para começar uma sessão nova |

**Resposta 202** (`AskResponse`):

```json
{ "question_id": "9f1c2e...", "session_id": "a650a2b8..." }
```

- `question_id`: identifica **esta execução**; use no GET de eventos abaixo.
- `session_id`: identifica **a conversa**. Se você mandou um, ele volta igual. Se não
  mandou, o servidor gera um novo — guarde-o e reenvie nas próximas perguntas da mesma
  conversa, ou cada pergunta vira uma conversa isolada, sem memória do que foi dito antes
  (ver `src/app/services/memory.py`).

**422**: `question` vazia/maior que o limite, ou `session_id` fora do tamanho permitido.

### `GET /api/v1/chat/questions/{question_id}/events`

`text/event-stream` (SSE): um evento por nó do grafo que termina, na ordem em que
acontecem, até o evento final.

**404**: `question_id` não existe (nunca foi criado, ou já expirou — ver "Expiração" abaixo).

**Formato de cada evento** (`AgentEvent`, uma linha `data: {...}\n\n` por evento):

| Campo | Tipo | Descrição |
|---|---|---|
| `node` | string | nó do grafo que acabou de rodar (ver tabela abaixo) |
| `label` | string | descrição curta em português, pronta para mostrar na UI |
| `detail` | string ou null | detalhe do que aconteceu nesse nó |
| `done` | bool | `true` só no evento final — é o último da stream |
| `answer` | string ou null | a resposta completa; só vem preenchida quando `done=true` |

Nós possíveis e o que `label`/`detail` mostram:

| `node` | `label` | O que aparece em `detail` |
|---|---|---|
| `triage` | Entendendo a pergunta | a intenção classificada: `chat` ou `data` |
| `optimize` | Selecionando tabelas e colunas | as tabelas escolhidas, ou que o catálogo está indisponível |
| `generate_sql` | Gerando a consulta SQL | o SQL gerado (se `status=ok`), ou a explicação (se não) |
| `validate_sql` | Validando a consulta | "consulta aprovada" ou o motivo da rejeição |
| `execute_sql` | Executando no banco | quantas linhas voltaram, ou o motivo da falha |
| `chat` **(final)** | Respondendo | a resposta, igual a `answer` |
| `finalize` **(final)** | Montando a resposta | a resposta, igual a `answer` |
| `error` **(final, só em falha inesperada)** | Erro inesperado | — |

Só `chat` e `finalize` (ou `error`) têm `done=true`; esses são sempre o **último** evento
da stream. Conectar depois do fim ainda funciona — o histórico é reproduzido do início antes
de fechar.

**Expiração**: resultados ficam guardados em memória do processo por
`CHAT_RESULT_TTL_S` (padrão 900s / 15 min) ou até `CHAT_RESULT_MAX` (padrão 200)
perguntas simultâneas serem excedidas — o que vier primeiro. Depois disso, o `question_id`
some e o GET passa a devolver 404. Não sobrevive a um restart do backend.

### `POST /api/v1/chat/questions/{question_id}/feedback`

Thumbs up/down da última resposta de uma conversa. Grava uma linha no **golden dataset**
(coleção `golden_data` no Mongo — `src/app/database/golden_data.py`), para alimentar testes
de regressão e medir melhora/piora do modelo no futuro.

`{question_id}` no caminho é só para log/correlação (aparece nos logs do backend e, se o
LangSmith estiver ligado, no trace) — a gravação em si não depende dele.

**Corpo da requisição** (`FeedbackRequest`):

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `session_id` | string | sim | a mesma conversa da pergunta avaliada |
| `question` | string | sim | a pergunta do usuário (até 2000 caracteres) |
| `answer` | string | sim | a resposta do agente (até 8000 caracteres) |
| `is_approved` | bool | sim | `true` = thumbs up, `false` = thumbs down |

**Resposta 201** (`FeedbackResponse`):

```json
{ "chat_range_id": "01a1995f-1174-7711-8773-ff8e117ff898" }
```

`chat_range_id` é um UUID v7 (ordenável pela hora de criação), gerado na hora — não depende
de nenhum contador no banco.

**422**: algum campo vazio ou maior que o limite.

O `context` gravado junto (não aparece na resposta, só no banco) é o resumo consolidado da
sessão, se já existir; sem resumo ainda, são os turnos recentes da conversa que seriam
usados para gerar um (ver `MemoryService.context_for_golden_record`).

---

## Fluxo completo, do ponto de vista de quem consome a API

```
1. POST /chat/questions            {"question": "..."}            → {question_id, session_id}
2. GET  /chat/questions/{id}/events  (SSE até done=true)          → resposta final
3. (usuário clica thumbs up/down)
4. POST /chat/questions/{question_id}/feedback
        {session_id, question, answer, is_approved}                → {chat_range_id}
5. Próxima pergunta da mesma conversa: repita o passo 1 reenviando o mesmo session_id.
```

## Auth

### `POST /api/v1/auth/login`

Corpo: `{"email": "...", "password": "..."}`. Resposta 200: `{"access_token": "...", "token_type": "bearer", "user": {id, name, email, role, created_at}}`.

- **401** com a mesma mensagem genérica para e-mail inexistente, senha errada ou usuário que não é admin (sem enumeração de contas; o tempo de resposta é equalizado com um hash descartável).
- **429** depois de `LOGIN_MAX_FAILURES` falhas por e-mail+IP dentro de `LOGIN_WINDOW_S`.
- O token é JWT HS256 e expira em `JWT_EXPIRE_MINUTES`. Com `ENV=prod`, `JWT_SECRET` é obrigatório.

### `GET /api/v1/auth/me`

Devolve o usuário do token (admin). **401** sem token.

---

## Produtos — vitrine pública

O dataset Olist não tem nome nem foto de produto: `label` é sintético (`categoria_en · #<8 primeiros caracteres do id>`).
Métricas consideram só pedidos que não foram `canceled`/`unavailable`. Nota e avaliações vêm do **pedido** (a Olist não avalia produtos), então um produto herda a nota dos pedidos em que apareceu.

### `GET /api/v1/products`

| Parâmetro | Padrão | Observação |
|---|---|---|
| `q` | — | busca no id e na categoria |
| `category` | — | nome em português ou inglês; `sem_categoria` para os sem categoria |
| `sort` | `units` | `units`, `rating`, `price_asc`, `price_desc` |
| `page`, `page_size` | 1, 24 | `page_size` de 1 a 100 |

Resposta: `{items: ProductSummary[], total, page, page_size}`. `ProductSummary`: `product_id, label, category, category_en, avg_price, avg_rating, review_count, units_sold, photos_qty`.

### `GET /api/v1/products/{product_id}`

`ProductSummary` + `weight_g, length_cm, height_cm, width_cm, name_length, description_length` + `related` (até 6 da mesma categoria). **404** se o produto não existe ou não teve venda válida.

### `GET /api/v1/categories`

`[{category, category_en, products, units_sold}]`, ordenado por unidades vendidas.

---

## Backoffice — análise de produtos (admin)

Todas exigem token de administrador (401/403). Os SQLs são constantes parametrizadas em `src/app/database/analytics.py` (placeholders `?`, ordenação por allowlist) e rodam no snapshot DuckDB somente leitura; o LLM não participa.

### `GET /api/v1/admin/overview`

`{kpis, monthly, top_categories, top_products}`. `kpis`: receita, unidades, pedidos, ticket médio, nota média, % de atraso, nº de produtos, vendedores e categorias. `monthly`: `[{month: "YYYY-MM", revenue, units, orders}]`.

### `GET /api/v1/admin/products`

Mesmos filtros da vitrine mais `min_rating` (0 a 5), `sort` (`units`, `revenue`, `rating`, `price`, `bad_review_pct`, `late_pct`) e `order` (`asc`/`desc`; padrão `revenue desc`). Cada linha acrescenta `revenue, freight_avg, bad_review_pct` (% de avaliações com nota ≤ 2), `late_pct` (% de pedidos entregues após a data estimada), `sellers` e `rank` (por receita). Parâmetro inválido: **422**.

### `GET /api/v1/admin/products/{product_id}`

Linha do produto + atributos físicos, `rating_distribution` (sempre 5 faixas), `monthly` e `top_sellers` (até 5). **404** se não existe.

### `GET /api/v1/admin/categories`

`[{category, category_en, products, units_sold, revenue, avg_price, avg_rating, bad_review_pct, late_pct, rank}]`.

---

## O que ainda não existe

- Endpoint de leitura do golden dataset (hoje só se grava, não se consulta pela API).
- Paginação/listagem de conversas ou perguntas passadas.
- Estado compartilhado entre workers: memória de sessão, resultados do chat e limiters ficam em memória do processo.
