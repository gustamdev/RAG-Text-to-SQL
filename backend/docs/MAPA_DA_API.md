# Mapa da API

Todas as rotas vivem sob o prefixo `/api/v1` (`API_VERSION` em `src/app/main.py`). Sem
autenticação hoje — qualquer chamador que alcance o backend pode usar qualquer rota.

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

## O que ainda não existe

- Autenticação/autorização — qualquer um que alcance a API pode usar qualquer rota.
- Endpoint de leitura do golden dataset (hoje só se grava, não se consulta pela API).
- Paginação/listagem de conversas ou perguntas passadas.
