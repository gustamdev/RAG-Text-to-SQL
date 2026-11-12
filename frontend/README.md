# Frontend

React 19 + TypeScript (strict) + Vite, com React Router, TanStack Query, Tailwind v4, shadcn/ui e Recharts.

Olist Insights tem três partes:

- **Vitrine pública** (`/`, `/produtos`, `/produtos/:id`): catálogo de produtos do dataset Olist, com busca, filtro por categoria, ordenação e paginação no servidor.
- **Backoffice** (`/backoffice/*`, só administradores): visão geral com KPIs e gráfico mensal, tabela de produtos com ordenação por coluna, detalhe do produto, ranking de categorias e o **Assistente de dados** (chat Text-to-SQL).
- O dataset não tem nome nem foto de produto: o backend envia um `label` sintético ("categoria · #abc12345") e a interface usa um ícone por categoria como imagem.

## Scripts

```bash
npm ci
npm run dev      # http://localhost:5173 (o proxy do Vite encaminha /api para http://localhost:8000)
npm run build    # tsc -b + vite build (saída em dist/)
npm run lint     # oxlint
npm test         # vitest run
```

## Rotas

| Rota | Tela | Acesso |
|---|---|---|
| `/` | Início: categorias principais e mais vendidos | público |
| `/produtos` | Catálogo (`?q`, `?category`, `?sort`, `?page`) | público |
| `/produtos/:id` | Detalhe do produto e relacionados | público |
| `/backoffice/login` | Entrar (e-mail e senha, sem criar conta; `?redirect=`) | público |
| `/backoffice` | Visão geral | admin |
| `/backoffice/produtos` | Tabela de produtos (`?q`, `?category`, `?min_rating`, `?sort`, `?order`, `?page`) | admin |
| `/backoffice/produtos/:id` | Métricas, notas, série mensal e vendedores | admin |
| `/backoffice/categorias` | Ranking de categorias | admin |
| `/backoffice/assistente` | Assistente de dados | admin |
| `/assistente` | Redireciona para `/backoffice/assistente` | — |

O estado das listas (busca, filtros, ordenação, página) vive na URL: dá para compartilhar o link e usar voltar/avançar.

## Login do administrador

- `POST /api/v1/auth/login` devolve um JWT. O token fica em `localStorage` (`olist.token`; só em memória se o navegador bloquear o storage) e vai no header `Authorization: Bearer` de toda chamada.
- Ao abrir o app, `GET /api/v1/auth/me` restaura a sessão. Token inválido ou de quem não é `admin` é descartado.
- `AuthProvider` recusa o login (e apaga o token) se o papel retornado não for `admin`.
- `RequireAdmin` protege `/backoffice/*` e redireciona para `/backoffice/login?redirect=...` (só caminhos internos são aceitos, ver `lib/navigation.ts`).
- Um 401 em qualquer chamada encerra a sessão local. A autorização real é do servidor.
- O cache do TanStack Query é limpo no login e no logout, e as chaves do backoffice incluem o id do admin.

## Assistente

`services/chat.ts` envia a pergunta com `POST /chat/questions` e acompanha a execução por SSE em `GET /chat/questions/{id}/events`. O stream usa `fetch` + `ReadableStream` (e não `EventSource`) para mandar o `Authorization`. O parser (`lib/sse.ts`) é uma função pura, testada com chunks partidos, `\r\n` e vários eventos por chunk. Erros 401, 403, 404 e 429 viram mensagens em português.

## Variáveis e ambiente

Não há variáveis `VITE_*`: a API é sempre `/api/v1` na mesma origem. Em desenvolvimento o proxy do Vite (`vite.config.ts`) leva `/api` ao backend na porta 8000. Em produção o `nginx.conf` faz o mesmo para `http://backend:8000`.

## Docker

`Dockerfile` em dois estágios: `node` gera o `dist` e `nginx-unprivileged` (usuário não-root, porta 8080) o serve com fallback de SPA e proxy de `/api` sem buffering (necessário para o SSE).

## Estrutura (`src/`)

| Pasta | Conteúdo |
|---|---|
| `app/` | `router.tsx` (rotas lazy), `AuthProvider`, `auth-context`, `RouteError` |
| `pages/Vitrine/` | Início, catálogo e detalhe público |
| `pages/Backoffice/` | Login, visão geral, produtos, detalhe do produto e categorias |
| `pages/Assistente/` | Chat, com CSS próprio isolado em `.assistente` |
| `components/layout/` | `PublicLayout`, `BackofficeLayout`, `Brand` |
| `components/product/` | `ProductCard`, `ProductThumb`, `RatingStars`, `Pagination`, `Specs` |
| `components/backoffice/` | `Sidebar`, `KpiCard`, `MonthlyChart`, `RatingBars`, `PageTitle` |
| `components/chat/` | `Composer`, `MessageList` |
| `components/ui/` | shadcn/ui escrito à mão (accordion, button, card, select nativo, sheet, table, ...) |
| `services/` | `http.ts` (fetch + JWT + erros tipados), `auth.ts`, `products.ts`, `backoffice.ts`, `chat.ts` |
| `hooks/` | `useProducts`, `useBackoffice`, `useAuth`, `useChat`, `useDebouncedValue`, `usePageTitle` |
| `types/` | `auth.ts`, `product.ts` (espelham os schemas do backend), `chat.ts` |
| `lib/` | `format`, `product`, `categoryIcons`, `pagination`, `searchParams`, `navigation`, `sse` (com testes) |

## Convenções

- Dados só vêm da API; nada além do token JWT é guardado no navegador.
- O catálogo tem cerca de 32 mil produtos: toda lista é paginada no servidor, nunca renderizada por inteiro.
- Estilo monocromático, cantos retos, fonte Archivo; utilities `display` e `eyebrow` em `index.css`.

## Créditos

Dados: [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Kaggle), licença CC BY-NC-SA 4.0, uso não comercial.
