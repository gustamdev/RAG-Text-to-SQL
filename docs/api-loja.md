# API da loja simulada: contrato (E1 a E6)

Contrato único para frontend e agentes de backend. Deriva de `docs/plano-loja-simulada.md` (v2) e `docs/loja-ux.md`. Documento de contrato original; a loja já foi implementada (confira o código em caso de divergência). Fundação (E0): tokens com `aud`, `POST /api/v1/auth/logout` do admin, índices e routers vazios. Onde o plano deixa decisão pendente do dono, está marcado **(pendente)**.

## 1. Convenções gerais

- Base: `/api/v1`. Os routers já existem, vazios, em `backend/src/app/api/routes/shop_*.py`, com prefixos `/shop/auth`, `/shop/products`, `/shop/cart`, `/shop/checkout`, `/shop/account`.
- JSON em UTF-8. Datas em ISO 8601 UTC (`2026-11-13T18:20:00Z`). **Dinheiro sempre em inteiros de centavos de BRL** (`*_cents`), nunca float. Peso em gramas (`weight_g`), dimensões em cm.
- Autenticação do cliente: `Authorization: Bearer <token>` com JWT `aud=shop`. Token de admin (`aud=admin`) nunca vale na loja, e token da loja nunca vale no admin (chaves de assinatura distintas por audiência). Claims: `sub` (id do cliente), `aud`, `jti`, `tv` (token_version), `exp`. O servidor compara `tv` com `token_version` do cliente a cada requisição; diferente = 401. Logout e exclusão de conta incrementam `token_version`.
- Rotas marcadas **público** não exigem token, mas passam pelo limitador por IP, com baldes SEPARADOS: catálogo (`enforce_catalog_rate_limit`), auth da loja (`enforce_auth_rate_limit`, 1/4 do limite público) e os públicos do dashboard (`enforce_public_rate_limit`). Rotas autenticadas da loja (carrinho, endereços, `/me`, `/logout`, frete) têm ainda limite por `customer_id` (`PUBLIC_RATE_LIMIT` por `PUBLIC_RATE_WINDOW_S`; a 121ª requisição em 1 min dá 429). Todos os padrões de CEP/OTP usam `[0-9]` (dígitos unicode, como árabes, dão 422).
- Erros: corpo `{"detail": "<mensagem em português>"}` (erros de domínio) ou o formato padrão do FastAPI para 422 (`{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`). Mensagens de autenticação são genéricas de propósito (sem enumeração de contas).
- Todos os corpos de entrada rejeitam campos desconhecidos (`extra="forbid"`, 422). O cliente nunca envia preço, total, frete, desconto, estado do pedido nem `customer_id`; tudo isso é calculado ou lido no servidor.
- Recurso de outro cliente (carrinho, endereço, pedido) responde **404**, igual a recurso inexistente (nunca 403), para não revelar existência.
- CORS: métodos `GET, POST, PATCH, DELETE, OPTIONS`; cabeçalhos `Authorization, Content-Type, Idempotency-Key`.

Códigos de erro usados:

| Código | Quando |
|---|---|
| 400 | Requisição semanticamente inválida (ex.: OTP inválido/expirado, mesma mensagem no bloqueio) |
| 401 | Sem token, token inválido/expirado/revogado, `aud` errado, credenciais incorretas |
| 402 | Não usado (recusa de pagamento é 200 com `payment.status="refused"`) |
| 404 | Inexistente ou de outro cliente |
| 409 | Conflito de estado (limite de itens/endereços, estoque insuficiente, transição inválida, `Idempotency-Key` reutilizada com outro corpo) |
| 422 | Validação de campos |
| 429 | Limite de taxa (envio de OTP, tentativas, IP) |
| 503 | Base de produtos indisponível |
| 504 | Timeout do gateway simulado (cartão final 0003) |

## 2. Tipos compartilhados

```jsonc
// Customer
{ "id": "9f1c...", "nickname": "Ana" /* ou null */, "email": "ana@exemplo.com",
  "terms_version": "1", "created_at": "2026-11-13T18:20:00Z" }

// ProductCard (listagem, sugestões, carrinho)
{ "product_id": "a1b2c3d4e5f6...", "title": "Cama, mesa e banho · Modelo A1B2",
  "category": "cama_mesa_banho", "category_label": "Cama, mesa e banho",
  "price_cents": 8990, "stock": 14, "avg_rating": 4.3 /* ou null */, "review_count": 128,
  "units_sold": 128, "photos_qty": 3 /* 1 a 5, nulo vira 1 */ }

// ProductDetail = ProductCard + dimensões
{ "...ProductCard", "weight_g": 1200, "length_cm": 32, "height_cm": 8, "width_cm": 24,
  "rating_distribution": { "5": 80, "4": 30, "3": 10, "2": 4, "1": 4 } }

// Page<T>
{ "items": [T], "total": 1240, "page": 1, "page_size": 24 }

// FreightOption
{ "code": "standard", "label": "Padrão", "price_cents": 1840, "days_min": 4, "days_max": 6 }
// codes: "standard" | "economy"

// CartLine
{ "product_id": "...", "title": "...", "category": "...", "unit_price_cents": 8990, "qty": 2,
  "line_total_cents": 17980, "stock": 14, "warning": null }
// warning: null | "stock_reduced" (qty ajustada ao estoque) | "out_of_stock" | "price_changed"

// Cart
{ "items": [CartLine], "item_count": 3 /* soma das qty */, "subtotal_cents": 22970,
  "blocked": false /* true se algum item tem warning != null e não foi confirmado */,
  "updated_at": "2026-11-13T18:20:00Z" }

// Address
{ "id": "...", "label": "Casa", "recipient": "Ana Souza", "zip": "01310100",
  "street": "Av. Paulista", "number": "1000", "complement": null, "district": "Bela Vista",
  "city": "São Paulo", "state": "SP", "is_default": true }

// Order
{ "order_id": "3f2a...(uuid4 hex)", "state": "created",
  "items": [{ "product_id": "...", "title": "...", "category": "...", "qty": 2,
              "unit_price_cents": 8990, "line_total_cents": 17980 }],
  "subtotal_cents": 17980, "freight_cents": 1840, "discount_cents": 0, "total_cents": 19820,
  "shipping": { "option": "standard", "label": "Padrão", "days_min": 4, "days_max": 6 },
  "address": { "recipient": "Ana Souza", "zip": "01310100", "street": "...", "number": "1000",
               "complement": null, "district": "Bela Vista", "city": "São Paulo", "state": "SP" },
  "payment": null /* ou { "status": "approved|refused|timeout", "brand": "visa", "last4": "0001" } */,
  "timeline": [{ "state": "created", "at": "2026-11-13T18:20:00Z" }],
  "reservation_expires_at": "2026-11-13T18:35:00Z" /* null depois de paid/canceled */,
  "created_at": "2026-11-13T18:20:00Z",
  "canceled_at": null /* ISO quando state=canceled */,
  "cancel_reason": null /* changed_mind|found_cheaper|wrong_item|delivery_too_long|other|expired|account_deleted */,
  "refund_cents": null /* canceled: total_cents se estava pago, senão 0 */ }

// OrderSummary (listas)
{ "order_id": "...", "state": "shipped", "total_cents": 22970, "item_count": 3, "created_at": "...",
  "canceled_at": null, "cancel_reason": null, "refund_cents": null }
```

Estados do pedido: `created`, `paid`, `refused`, `shipped`, `delivered`, `canceled`. Transições válidas (o servidor valida; o cliente nunca define estado):

```
created -> paid | refused | canceled
refused -> paid | canceled
paid    -> shipped | canceled
shipped -> delivered
```

`shipped` e `delivered` avançam por simulação interna do servidor (sem endpoint). Pedido em `created`/`refused` com `reservation_expires_at` vencido vira `canceled` (`cancel_reason: expired`) e devolve o estoque; exclusão de conta cancela os abertos com `cancel_reason: account_deleted`. Mensagem de transição inválida: 409 `"Esta ação não é permitida para o estado atual do pedido."`.

## 3. shop/auth

Fluxos: cadastro = `signup` + `verify-otp`; login = `login` + `login/verify-otp` (MFA por e-mail a cada login; "confiar neste dispositivo" **adiado**: não implementado, `device_token`/`trust_device` fora do contrato). OTP: 6 dígitos, HMAC com pepper, expira em `OTP_TTL_S` (300 s), `OTP_MAX_ATTEMPTS` (5) tentativas, novo OTP invalida o anterior, descartado ao usar. Envio: cooldown `OTP_RESEND_COOLDOWN_S` (60 s), máx. `OTP_MAX_SENDS_PER_HOUR` (3) por e-mail e limite por IP, persistidos no Mongo. O envio de `login` tem baldes PRÓPRIOS (`rate_lsend_*`) que só contam quando a senha foi aceita: cadastro/reenvio anônimos não bloqueiam o login do dono. Chutes de verificação contam por (e-mail, IP-pseudônimo) dentro do OTP (`ip_attempts`, 5 por IP) e no total (4 x 5): um IP estranho esgota só a própria cota. `MAIL_BACKEND=console` imprime o código no log do servidor (proibido em prod).

### POST /shop/auth/signup (público)

Body: `{"nickname": "Ana" (opcional, 1-40), "email": "ana@exemplo.com", "password": "min 12, max 128", "accept_terms": true, "accept_adult": true, "terms_version": "1"}`.
`accept_terms` e `accept_adult` precisam ser `true`; `terms_version` precisa ser a vigente.
Conta pendente (não verificada) some em 24 h (`pending_expires_at`, TTL; removido no verify). Com OTP de cadastro vivo, um novo `signup` no mesmo e-mail só reenvia o código e NÃO troca a senha pendente. Risco residual: depois do OTP expirar o último cadastro pendente vence; como o login sempre exige OTP enviado ao e-mail do dono, quem cadastrou primeiro não entra sem acesso à caixa de entrada. O aceite grava o evento `terms_accepted` (versão em `meta`) na auditoria.

Resposta **202** idêntica para e-mail novo, pendente ou já existente: `{"detail": "Se o e-mail puder ser usado, enviamos um código."}`.
Erros: 422 (senha curta, aceite ausente, e-mail inválido), 429.

### POST /shop/auth/verify-otp (público)

Body: `{"email": "...", "code": "123456"}` (6 dígitos). Verifica o e-mail do cadastro e já autentica.
Resposta 200: `{"access_token": "...", "token_type": "bearer", "customer": Customer}`.
Erros: 400 `"Código inválido ou expirado"` (mensagem única para qualquer causa, inclusive bloqueio após 5 erros: o lockout nunca é revelado), 429 (só vem do limite de envio/IP, nunca da verificação).

### POST /shop/auth/resend-otp (público)

Body: `{"email": "...", "purpose": "signup" | "login"}`. Resposta 202 `{"detail": "Se o e-mail puder ser usado, enviamos um código."}` sempre (login só reenvia se a senha já foi aceita). 429 quando vale cooldown/limite (`{"detail": "Aguarde para pedir um novo código."}`).

### POST /shop/auth/login (público)

Body: `{"email": "...", "password": "..."}`.
Resposta 202 `{"mfa_required": true, "masked_email": "a***@exemplo.com"}` e envia o OTP.
Erros: 401 `"E-mail ou senha incorretos."` (igual para e-mail inexistente, senha errada, conta não verificada ou excluída), 429 (bloqueio por tentativas, com atraso progressivo por e-mail). Os contadores de falha são persistidos no Mongo (`rate_login_email`, `rate_login_ip`, `rate_login_pair`: HMAC, janela `LOGIN_WINDOW_S`, `$inc` atômico) e sobrevivem a restart e a flood de chaves. O 429 de limite de envio vem ANTES da checagem da senha: não revela se ela está certa.

### POST /shop/auth/login/verify-otp (público)

Body: `{"email": "...", "code": "123456"}`.
Resposta 200: `{"access_token": "...", "token_type": "bearer", "customer": Customer}`.
Erros: 400 (mesmas mensagens de `verify-otp`), 429.

### POST /shop/auth/forgot-password (público)

Body: `{"email": "..."}`. Resposta **202** sempre igual, exista a conta ou não: `{"masked_email": "a***@exemplo.com", "message": "Se o e-mail existir, enviamos um código."}`. Só conta verificada e não excluída recebe OTP `purpose="reset"` (mesmos TTL, pepper, tentativas e cooldown; envio com baldes PRÓPRIOS `rate_rsend_*`, contados sempre). Erros: 422 (e-mail inválido), 429 (`"Aguarde para pedir um novo código."`, igual para qualquer e-mail).

### POST /shop/auth/reset-password (público)

Body: `{"email": "...", "code": "123456", "new_password": "min 12, max 128"}`. Resposta **200** `{"ok": true}`. Troca a senha, incrementa `token_version` (revoga todas as sessões), apaga OTPs pendentes (`reset` e `login`) do e-mail, audita `password_reset` e envia aviso "Sua senha foi alterada". Não autentica: o cliente entra pelo login normal.
Erros: 400 `"Código inválido ou expirado."` (qualquer falha: código errado, expirado, reusado, 5 erros, conta inexistente/não verificada/excluída), 422 (senha curta; não consome o código), 429 (limite por IP).

### POST /shop/auth/logout (cliente)

Sem body. Incrementa `token_version` (revoga todos os tokens do cliente). Resposta **204**. Erros: 401.

### GET /shop/auth/me (cliente)

Resposta 200: `Customer` (inclui `phone`, só dígitos ou null). Erros: 401.

## 4. shop/products (público)

Todas as rotas desta seção: sem token, limitador por IP, 503 se a base estiver indisponível. A ordem das rotas no router precisa colocar `categories` e `suggest` antes de `{product_id}`.

### GET /shop/products

Query: `q` (texto, 1-80), `category`, `min_price_cents`, `max_price_cents`, `min_rating` (1 a 5), `min_reviews` (inteiro 1 a 10^9, mínimo de avaliações; preços 0 a 10^9), `in_stock` (bool), `sort` (`best_selling` padrão | `price_asc` | `price_desc` | `rating` | `newest`), `page` (1 a 100000), `page_size` (1-48, padrão 24).
Resposta 200: `Page<ProductCard>`. Sem resultado: `items: []`, `total: 0`. Erros: 422, 429, 503.

### GET /shop/products/categories

Resposta 200: `[{"category": "cama_mesa_banho", "label": "Cama, mesa e banho", "product_count": 1240}]`, ordenado por `product_count` decrescente.

### GET /shop/products/suggest?q=

`q` com 2 a 80 caracteres; casa por PREFIXO (título ou categoria), literal. A lista de categorias fica em cache de 60 s por processo (`/categories` e `suggest`). Listagens têm `maxTimeMS`. Resposta 200: `{"products": [ProductCard] /* até 5 */, "categories": [{"category": "...", "label": "..."}] /* até 3 */}`.

### POST /shop/products/batch (público)

Para o carrinho de convidado (`localStorage`): preço e estoque atuais. Body: `{"ids": ["...", "..."]}` (1 a 50 ids). Resposta 200: `{"items": [ProductCard]}`; ids inexistentes são omitidos (sem 404). Declarar esta rota antes de `{product_id}`. Erros: 422 (mais de 50 ou lista vazia), 429, 503.

### GET /shop/products/{product_id}

Resposta 200: `ProductDetail`. Erros: 404 `"Produto não encontrado."`.

### GET /shop/products/{product_id}/freight?zip=01310100

`zip`: 8 dígitos (aceita `01310-100`; normalizado). Frete: haversine entre o prefixo de CEP do depósito (`SHOP_ORIGIN_ZIP_PREFIX`, tabela `geolocation` do Olist) e o destino, mais peso. O destino usa `lat`/`lng` do CEP real (mesmo serviço e cache de `/shop/zip`) quando a BrasilAPI os devolve; sem eles ou sem rede, usa o prefixo (continua funcionando offline). Não grava CEP nem coordenadas do cliente. Limitação aceita: prefixo de CEP é impreciso (demo).
Resposta 200: `{"zip": "01310100", "options": [FreightOption, FreightOption]}`.
Erros: 404 (produto), 422 `"CEP inválido."` (formato ou prefixo sem coordenada).

### GET /shop/zip/{zip}

Público. `zip`: exatamente 8 dígitos, sem hífen. O servidor resolve o CEP (o navegador nunca chama API externa): cache em memória (7 dias; desconhecido, 10 min) -> BrasilAPI -> ViaCEP -> prefixo de 5 dígitos da coleção `geolocation` (offline, só cidade/UF). Timeout de 3 s por API, sem redirects, circuit-breaker (3 falhas seguidas pausam a API por 60 s) e texto das APIs validado/truncado.
Resposta 200: `{"zip": "01310100", "street": "Avenida Paulista", "district": "Bela Vista", "city": "São Paulo", "state": "SP", "lat": -23.56, "lng": -46.65, "source": "brasilapi"}`. `source`: `brasilapi`, `viacep` ou `offline`; campos ausentes = `null` (offline: cidade como no dataset, minúscula sem acento; `lat`/`lng` só vêm da BrasilAPI). `Cache-Control: public, max-age=3600` (300 no offline).
Erros: 404 `"CEP não encontrado."` (nenhuma fonte conhece), 422 (formato), 429 (balde por IP de `PUBLIC_RATE_LIMIT // 4`, mais estrito que o catálogo porque pode disparar chamada externa). `ZIP_API_ENABLED=false` desliga as APIs (só offline).

## 5. shop/cart (cliente)

Carrinho no servidor, um por cliente. Limites: `SHOP_CART_MAX_ITEMS` (50 linhas), `SHOP_CART_MAX_QTY` (10 por linha), TTL `SHOP_CART_TTL_DAYS` (30) desde `updated_at`. Toda resposta devolve o `Cart` recalculado com preço e estoque atuais; o servidor guarda só `product_id` e `qty`. Todas exigem token (401).

### GET /shop/cart

Resposta 200: `Cart` (vazio: `items: []`, totais 0).

### POST /shop/cart/items

Body: `{"product_id": "...", "qty": 1}` (qty 1 a 10). Soma à linha existente, respeitando o teto de 10 e o estoque.
Resposta 200: `Cart`. Erros: 404 (produto), 409 `"Produto sem estoque suficiente."` ou `"Limite de itens do carrinho atingido."`, 422.

### PATCH /shop/cart/items/{product_id}

Body: `{"qty": 3}` e/ou `{"ack": true}` (qty 1 a 10; para remover use DELETE; ao menos um dos dois). `ack=true` confirma o aviso `price_changed`/`stock_reduced` da linha (o servidor guarda o preço/qty confirmados) e limpa `blocked` quando não restar linha sem confirmação; `out_of_stock` não se confirma, só se remove. Resposta 200: `Cart`. Erros: 404 (linha não está no carrinho), 409 (estoque), 422.

### DELETE /shop/cart/items/{product_id}

Resposta 200: `Cart` sem a linha. Erros: 404 (linha inexistente).

### DELETE /shop/cart

Esvazia. Resposta 200: `Cart` vazio.

### POST /shop/cart/merge

Mescla o carrinho de convidado (guardado em `localStorage`) ao entrar. Body: `{"items": [{"product_id": "...", "qty": 1}]}` (até 50). Itens inválidos ou sem estoque são ignorados (não falha a requisição). Resposta 200: `Cart`.

### POST /shop/cart/freight

Frete do carrinho inteiro (peso somado). Body: `{"zip": "01310100"}` **ou** `{"address_id": "..."}` (exatamente um; `address_id` precisa ser do cliente, outro cliente = 404). `GET /shop/cart/freight?zip=` continua valendo só para `zip`. Resposta 200: `{"zip": "...", "options": [FreightOption]}`. Erros: 409 `"Carrinho vazio."`, 422 `"CEP inválido."`.

## 6. shop/checkout (cliente)

Pagamento 100% simulado: **nenhum valor é cobrado**. Duas etapas: criar o pedido (reserva estoque) e pagar. Ambas exigem o cabeçalho `Idempotency-Key` (8 a 64 caracteres `[A-Za-z0-9_-]`, gerada pelo cliente, **uma chave diferente por operação**). Índice único `(customer_id, scope, key)` (`scope` = `checkout` | `pay`) mais hash do corpo, TTL 24 h. Repetir a mesma chave com o mesmo corpo devolve a resposta original (mesmo pedido, sem novo desconto de estoque, mesmo código HTTP). Respostas 504/timeout **não** são persistidas em `shop_idempotency`: repetir a chave reexecuta o pagamento. Claim sem resposta há mais de 300 s (processo morreu) é retomado pela próxima requisição; antes disso a repetição recebe 409 `"Requisição em andamento..."`. Mesma chave com corpo diferente: 409 `"Idempotency-Key já usada com outro conteúdo."`. Sem o cabeçalho: 422.

### POST /shop/checkout

Header: `Idempotency-Key`. Body: `{"address_id": "...", "shipping_option": "standard" | "economy"}`.
O servidor lê o carrinho, revalida preço e estoque, calcula frete pelo CEP do endereço, reserva o estoque item a item (`find_one_and_update` com `$gte`/`$inc`, sem transação), cria o pedido em `created` com `reservation_expires_at` (15 min). O carrinho **não** é esvaziado aqui: só quando o pagamento é aprovado (cancelar/expirar não perde o carrinho). Máx. 3 pedidos abertos (`created`/`refused`) por cliente; o peso do frete vem dos mesmos itens do pedido. Um job no lifespan cancela reservas vencidas a cada 60 s (`SHOP_EXPIRE_INTERVAL_S`) e devolve o estoque.
Resposta **201**: `Order` (`payment: null`).
Erros: 404 (endereço de outro cliente ou inexistente), 409 `"Carrinho vazio."` / `"Você já tem pedidos em aberto..."` / `"Estoque insuficiente."` (com `"items": [{"product_id": "...", "available": 0}]` no corpo junto de `detail`, e a reserva parcial é desfeita), 422, 429.

### POST /shop/checkout/{order_id}/pay

Header: `Idempotency-Key`. Body:

```json
{ "card_number": "4111111111110001", "holder": "ANA SOUZA", "exp_month": 12, "exp_year": 2030, "cvv": "123" }
```

Cartão salvo no lugar de cartão novo: `{ "saved_card_id": "<id de GET /shop/account/cards>", "cvv": "123" }` (misturar as duas formas: 422; cartão de outro cliente ou inexistente: 404 sem gastar tentativa). Cartão novo aceita `"save_card": true` para salvar o cartão se o pagamento for aprovado; o **padrão é `false`** (privacy by default) e o campo é ignorado com `saved_card_id`. Sem vaga (limite de 3) ou falha ao salvar: o pagamento segue 200. O `body_hash` de `pay` é HMAC (chave do servidor) de `order_id` + PAN com escopo do cliente (`pan:<customer_id>:<PAN>`, sem correlação entre contas) ou `order_id` + `saved:<saved_card_id>`; nunca o PAN em claro. Cartões de teste pelos últimos 4 dígitos: `0001` aprova, `0002` recusa, `0003` simula timeout. Número com Luhn inválido: 422 `"Número de cartão inválido."` sem gastar tentativa; Luhn válido fora da lista: recusado (o PAN real nunca é gravado nem logado: o servidor guarda só bandeira e últimos 4; `holder`, `cvv` e PAN completo são descartados). O valor cobrado é sempre `order.total_cents` do servidor.
Resposta 200: `{"order": Order, "payment": {"status": "approved" | "refused", "brand": "visa", "last4": "0001"}}`. A transição é uma atualização condicional (`update_one({order_id, state: {$in: ["created","refused"]}}, state="paid")`): só quem a vence aprova, então o pagamento nunca é aprovado duas vezes. Quem perde a corrida depois de cobrar (aprovado sem transição) grava `status: "refunded"` em `shop_payments` apenas se ainda não houver pagamento `approved` do pedido; o doc do vencedor nunca é sobrescrito. Aprovado: pedido vai a `paid` e a reserva vira definitiva. Recusado: pedido vai a `refused` (pode pagar de novo ou cancelar).
Timeout (cartão 0003): **504** `{"detail": "Não conseguimos confirmar. Tente novamente."}`; o status `timeout` existe só em `shop_payments`, a Order segue `created` (sem `payment`) e a resposta não é gravada. O cliente repete (pode reusar a `Idempotency-Key`): o pagamento é reexecutado sobre o mesmo documento de `shop_payments` do pedido (um por `order_id`).
A tentativa é contada atomicamente ANTES de cobrar (teto 5 por pedido, mesmo com requisições paralelas). Falha ao gravar o pagamento/limpar o carrinho depois de o pedido virar `paid` é logada e a resposta 200 é mantida. Erros: 404 (pedido de outro cliente), 409 (estado não permite pagar, ou reserva expirada: `"Reserva expirada. Refaça o pedido."`), 422, 429.

## 7. shop/account (cliente)

### Endereços (máx. `SHOP_MAX_ADDRESSES` = 3)

- `GET /shop/account/addresses` -> 200 `[Address]`.
- `POST /shop/account/addresses` -> 201 `Address`. Body: `{"label": "Casa", "recipient": "Ana Souza", "zip": "01310100", "street": "...", "number": "1000", "complement": null, "district": "...", "city": "...", "state": "SP", "is_default": false}`. `label` 1-30, `zip` 8 dígitos, `state` UF válida, demais textos até 120. Erros: 409 `"Limite de 3 endereços atingido."`, 422. `city`/`state` são sobrescritos pelo servidor a partir do CEP (API ou base offline) quando conhecido, para o frete não depender da UF digitada; CEP desconhecido mantém o digitado.
- `PATCH /shop/account/addresses/{address_id}` -> 200 `Address`. Body: qualquer subconjunto dos campos do POST. Erros: 404, 422.
- `DELETE /shop/account/addresses/{address_id}` -> **204**. Pedidos já criados mantêm sua cópia do endereço. Erros: 404.

Marcar `is_default: true` desmarca o anterior. O primeiro endereço nasce padrão.

### Cartões salvos (máx. 3, pagamento simulado)

- `GET /shop/account/cards` -> 200 `[{"id","brand","last4","exp_month","exp_year"}]` (ordem de criação).
- `POST /shop/account/cards` -> **201** `Card` quando cria; **200** com o cartão existente quando o mesmo PAN já está salvo (a validade `exp_month`/`exp_year` do existente é atualizada). Body (`extra="forbid"`): `{"card_number": "4242 4242 4242 0001", "holder": "ANA SOUZA", "exp_month": 12, "exp_year": 2030, "cvv": "123"}`; PAN 13-19 dígitos com Luhn válido (ou cartão de teste), cartão vencido: 422. Limite: 409 `"Limite de 3 cartões atingido."` (duplicata no limite ainda devolve 200). Só são gravados bandeira, `last4`, validade, impressão digital (HMAC do PAN com escopo do cliente) e o resultado simulado; nunca PAN, CVV nem titular. Auditoria `card_added` só com o id.
- `DELETE /shop/account/cards/{card_id}` -> **204**. Cartão de outro cliente = 404. Auditoria `card_removed`.
- Escritas passam pelo limitador de escrita da conta (429). Pagar com `saved_card_id`: ver `POST /shop/checkout/{order_id}/pay`.

### Pedidos

- `GET /shop/orders?page=1&page_size=20` (page_size 1-50) -> 200 `Page<OrderSummary>`, mais recentes primeiro, só do cliente logado.
- `GET /shop/orders/{order_id}` -> 200 `Order` (inclui `timeline`). Erros: 404. É também a fonte da tela de confirmação.
- `POST /shop/orders/{order_id}/cancel` -> 200 `Order` em `canceled`. Corpo opcional `{"reason": "changed_mind"|"found_cheaper"|"wrong_item"|"delivery_too_long"|"other"}` (ausente = `other`; campo extra ou valor fora da lista = 422). Cancela de `created`, `refused` e `paid` (pago e ainda não enviado) e devolve o estoque. De `paid`: reembolso simulado (`refund_cents` = `total_cents`; o pagamento mantém `status: approved` e ganha `refund: {amount_cents, at}`). O pedido grava `canceled_at`, `cancel_reason`, `canceled_from` (`created|refused|paid`), `refund_cents` e o evento `canceled` na timeline. `shipped`/`delivered`: 409 `"Pedido já enviado: não pode ser cancelado."` (devolução fora do escopo); já cancelado: 409 (mensagem de transição inválida). Cancelar x pagar x expirar: transição condicional, um só vence. Erros: 404.

### Perfil, exportação e exclusão (LGPD)

- `PATCH /shop/account` -> 200 `{"id","nickname","email","phone"}`. Body (`extra="forbid"`, ao menos um campo): `{"nickname": "Ana", "phone": "(11) 98765-0000"}`; telefone guardado só com dígitos (10 ou 11), `null` limpa. Erros: 422.
- `GET /shop/account/export` -> 200 JSON só do cliente logado: `{"exported_at", "customer": {id, email, nickname, phone, terms_version, terms_accepted_at, created_at, last_login_at}, "addresses": [...], "orders": [...], "payments": [{status, brand, last4, amount_cents, ...}], "cards": [{id, brand, last4, exp_month, exp_year, created_at}], "cart": {"items": [...]} | null}`. Sem hash de senha, sem PAN, sem impressão digital do cartão. `orders` e `payments` seguem allowlist (sem `payment_id`, `reservation_expires_at`, `timeline`, idempotência). Resposta com `Cache-Control: no-store` e `Content-Disposition: attachment; filename="meus-dados.json"`. Grava auditoria `dsar_export`.
- `PATCH /shop/account/password` -> **204** (sem corpo). Body (`extra="forbid"`): `{"current_password": "...", "new_password": "min 12, max 128", "code": "opcional"}`. Sem OTP de reautenticação: a senha atual é a prova; `code` é aceito e descartado (compatibilidade com o frontend). Incrementa `token_version` (derruba TODAS as sessões, inclusive a atual: o cliente faz logout e entra de novo), grava auditoria `password_changed` e envia e-mail de aviso. Senha atual errada: 401 `"Senha atual incorreta."` (auditoria `password_change_fail`); contador persistido por cliente (HMAC, `rate_change_pw`), teto 5 por `LOGIN_WINDOW_S`, depois 429 (mesmo com a senha certa). Nova senha igual à atual: 422 `"A nova senha deve ser diferente da atual."`. Demais erros: 401 (sem token/sessão revogada), 422, 429.
- `DELETE /shop/account` -> **204**. Body JSON: `{"password": "...", "confirm": "EXCLUIR"}` (reautenticação pela senha mais confirmação digitada; sem OTP nesta versão). Apaga endereços, cartões salvos, carrinho e registros de `shop_idempotency`; anonimiza o cliente (e-mail vira `deleted-<id>@anon.invalid`, apelido, telefone e hash nulos, `deleted_at`), os pedidos (endereço de entrega, `payment.brand` e `payment.last4` zerados; valores e itens mantidos) e os pagamentos (`brand`/`last4` nulos); incrementa `token_version` (o token deixa de valer); pede refresh do snapshot do agente; grava auditoria `account_deleted` sem PII. Ordem: reautentica, anonimiza o cliente primeiro (`token_version`+1, `deleted_at`), depois limpa pedidos, endereços, carrinho, idempotência (de novo ao final) e `shop_otp` do e-mail; a limpeza pode ser repetida em conta já com `deleted_at`. Falha de auditoria não aborta. Senha errada: 401 `"Senha incorreta."`; contador persistido por cliente (HMAC, `rate_delete_pw`), teto 5 por `LOGIN_WINDOW_S`, depois 429 (mesmo com senha certa); ambos gravam `delete_fail`. Erros: 401, 422, 429.

### Termos e privacidade (público)

- `GET /shop/legal` -> 200 `{"version": "1", "terms": "...", "privacy": "..."}` (texto simples).

### Backoffice da loja (admin, aud=admin; PII mascarada)

- `GET /admin/shop/customers?page=1&page_size=20` -> `{items: [{id, email: "a***@dominio", phone: "*********21", nickname: "A*** S***", created_at, deleted}], total, page, page_size}`.
- `GET /admin/shop/orders?page=1&page_size=20` -> `{items: [{order_id, customer_id, state, total_cents, created_at, recipient: "A*** S***", zip: "013*****", city, state_uf}], ...}`.
- Cada consulta grava auditoria `admin_view_customers` / `admin_view_orders` (ator e `ip_hmac` em HMAC, TTL de 365 dias via `expires_at`; demais eventos 90 dias). Limite por admin (`ADMIN_SHOP_RATE_LIMIT`/`ADMIN_SHOP_RATE_WINDOW_S`, 60/60 s, em memória): excedido -> 429. Índice `shop_customers.created_at`. Nunca devolve e-mail, telefone, CEP ou nome completos.

### Retenção LGPD e configuração

Loop diário no lifespan (`_expire_loop`, junto da expiração de reservas): roda a cada `SHOP_RETENTION_INTERVAL_S` (86400 s; avança também após falha, sem repetir a cada 60 s). Em lotes de 500, até esvaziar:

- `SHOP_UNVERIFIED_TTL_HOURS` (24): apaga contas sem e-mail verificado e seus OTPs.
- `SHOP_RETENTION_INACTIVE_DAYS` (730): anonimiza contas sem login (condicional no banco: quem logou durante o passe fica).
- `SHOP_RETENTION_ORDER_DAYS` (1825): apaga pedidos e pagamentos encerrados e contas já anonimizadas mais antigas que isso.

Refresh do snapshot pendente (`shop_flags`) é repetido a cada ciclo de 60 s: o marcador é limpo antes do pedido e recriado se ele falhar. Padrões são placeholders a validar pelo dono.

## 8. Coleções MongoDB `shop_*`

Banco `MONGO_DB_NAME`. Proibido juntar `shop_*` com as tabelas Olist (`customers` etc.). PII = dado pessoal direto ou indireto, sujeito a LGPD (exportar, corrigir, excluir). Índices criados por `app/database/indexes.py::ensure_indexes` (idempotente). Datas são `datetime` UTC no Mongo.

### shop_customers

| Campo | Tipo | PII | Nota |
|---|---|---|---|
| `_id` | str (uuid4 hex) | indireto | id do cliente (`sub` do token) |
| `email` | str | **sim** | minúsculo, **único** |
| `nickname` | str ou null | **sim** | opcional |
| `password_hash` | str | segredo | argon2id |
| `email_verified` | bool | não | falso até o primeiro OTP de cadastro |
| `token_version` | int | não | default 0; `$inc` no logout/exclusão |
| `terms_version` | str | não | versão aceita |
| `terms_accepted_at` | datetime | não | |
| `adult_confirmed` | bool | não | 18+ |
| `created_at`, `last_login_at` | datetime | não | |
| `deleted_at` | datetime ou null | não | exclusão lógica antes da purga |

Índices: `email` único. (`token_version` é campo, não precisa de índice: só é lido por `_id`.)

### shop_otp

Guarda OTPs e também os contadores de envio persistidos (não em memória).

| Campo | Tipo | PII | Nota |
|---|---|---|---|
| `_id` | str | não | |
| `email` | str | **sim** | nos docs `rate_email` e `rate_ip`, guarda o HMAC (`PSEUDONYM_KEY`) do e-mail/IP, não o valor |
| `purpose` | str | não | `signup`, `login`, `rate_email`, `rate_ip` (cadastro/reenvio), `rate_lsend_email`, `rate_lsend_ip` (envio de login), `rate_login_email`, `rate_login_ip`, `rate_login_pair` (falhas de login; campo `n`) |
| `code_hash` | str ou null | segredo | HMAC-SHA256 do código com `OTP_PEPPER`; nulo nos contadores |
| `attempts` | int | não | chutes do OTP (total); `ip_attempts` guarda por IP-pseudônimo |
| `sends` | int | não | contador na janela de 1 h (`$inc` atômico) |
| `last_sent_at` | datetime | não | cooldown |
| `created_at` | datetime | não | |
| `expires_at` | datetime | não | **TTL** (`expireAfterSeconds=0`); a checagem de `expires_at` também acontece no código. Nos contadores `rate_email`/`rate_ip`, `expires_at` >= 1 h desde o início da janela (senão o TTL apagaria o contador antes do fim da janela) |

Índices: `expires_at` (TTL), `(email, purpose)` **único** (um documento por par; reenvio faz upsert).

### shop_carts

| Campo | Tipo | PII | Nota |
|---|---|---|---|
| `_id` | str | não | |
| `customer_id` | str | indireto | **único** |
| `items` | list de `{product_id, qty, added_at}` | não | sem preço (recalculado) |
| `updated_at` | datetime | não | **TTL** `SHOP_CART_TTL_DAYS` dias |

### shop_addresses

| Campo | Tipo | PII |
|---|---|---|
| `_id` | str | não |
| `customer_id` | str | indireto |
| `label` | str | não |
| `recipient`, `zip`, `street`, `number`, `complement`, `district`, `city`, `state` | str | **sim** (todos) |
| `is_default` | bool | não |
| `created_at`, `updated_at` | datetime | não |

Índices: `customer_id`. Máx. 3 por cliente.

### shop_products

Sem PII. Semeada a partir do Olist (preço = mediana de `order_items.price`; estoque inicial `SHOP_FREE_STOCK_DEFAULT`).

| Campo | Tipo | Nota |
|---|---|---|
| `product_id` | str | **único**, id do produto Olist |
| `category`, `category_label` | str | índice em `category` |
| `title` | str | derivado (`Categoria · Modelo AB12`) |
| `price_cents` | int | |
| `stock` | int | nunca < 0 (decremento condicional `$gte`). Seed: regra determinística por produto (~2% zerados, ~10% com 1-5, resto 15-150); `uv run python scripts/seed_shop.py --restock` reaplica a TODOS (manual) |
| `weight_g`, `length_cm`, `height_cm`, `width_cm` | number ou null | |
| `photos_qty`, `review_count`, `units_sold` | int | |
| `avg_rating` | float ou null | |
| `updated_at` | datetime | |

### shop_orders

| Campo | Tipo | PII | Nota |
|---|---|---|---|
| `order_id` | str (uuid4 hex) | não | **único** |
| `customer_id` | str ou null | indireto | nulo após exclusão da conta |
| `state` | str | não | `created, paid, refused, shipped, delivered, canceled` |
| `items` | list de `{product_id, title, category, qty, unit_price_cents, line_total_cents}` | não | |
| `subtotal_cents`, `freight_cents`, `discount_cents`, `total_cents` | int | não | calculados no servidor |
| `shipping` | `{option, label, days_min, days_max}` | não | |
| `address` | `{recipient, zip, street, number, complement, district, city, state}` | **sim** | cópia no momento da compra; anonimizada na exclusão (fica `zip` 3 dígitos, `city`, `state`) |
| `payment_id` | str ou null | não | |
| `timeline` | list de `{state, at}` | não | |
| `reservation_expires_at` | datetime ou null | não | reconciliação de reservas órfãs |
| `created_at`, `updated_at` | datetime | não | |

Índices: `(customer_id, created_at desc)`, `order_id` único, `(state, reservation_expires_at)` (reconciliação de reservas), `payment_id`.

### shop_payments

| Campo | Tipo | PII | Nota |
|---|---|---|---|
| `payment_id` | str | não | índice |
| `order_id` | str | não | **único** (um documento por pedido, atualizado a cada tentativa de pagamento) |
| `customer_id` | str ou null | indireto | nulo após exclusão da conta |
| `status` | str | não | `approved, refused, timeout` (`timeout` só aqui; a Order não ganha esse estado) |
| `brand`, `last4` | str | indireto | tratar `last4` como dado pessoal; **nunca** PAN, CVV nem titular |
| `amount_cents` | int | não | |
| `created_at` | datetime | não | |

### shop_cards

| Campo | Tipo | PII | Nota |
|---|---|---|---|
| `_id` | str | não | id do cartão (`saved_card_id`) |
| `customer_id` | str | indireto | índice único `(customer_id, fingerprint)`; toda query filtra por ele |
| `brand`, `last4`, `exp_month`, `exp_year` | str, str, int, int | indireto | tratar como dado pessoal; **nunca** PAN, CVV nem titular |
| `fingerprint` | str | indireto | HMAC do PAN com escopo do cliente (`pan:<customer_id>:<PAN>`); só detecta duplicata |
| `outcome` | str | não | resultado simulado (`approved`, `refused`, `timeout`); com gateway real vira token do provedor |
| `created_at` | datetime | não | |

Retenção: até o cliente excluir o cartão ou a conta (`delete_all` na exclusão).

### shop_idempotency

| Campo | Tipo | PII | Nota |
|---|---|---|---|
| `customer_id` | str | indireto | |
| `key` | str | não | `(customer_id, scope, key)` **único** |
| `scope` | str | não | `checkout` ou `pay` |
| `body_hash` | str | não | SHA-256 do corpo normalizado |
| `status_code`, `response` | int, objeto | **sim** | guarda o `OrderOut` inteiro (endereço, destinatário: PII); TTL 24 h |
| `token` | str | não | dono do claim: `complete`/`release` só valem com ele |
| `created_at` | datetime | não | **TTL** 24 h |

### shop_audit

Sem PII: a identidade é pseudonimizada com HMAC (`PSEUDONYM_KEY`), nunca e-mail, IP ou id em claro.

| Campo | Tipo | Nota |
|---|---|---|
| `_id` | str | |
| `event` | str | `signup, terms_accepted, otp_sent, login_ok, login_fail, logout, order_created, order_paid, order_canceled, export, account_deleted` |
| `actor` | str | HMAC do `customer_id` (ou do e-mail em falhas de login) |
| `ip_hmac` | str ou null | HMAC da rede do IP (IPv4 truncado ao /24), só em `login_fail` e `otp_sent`; nulo nos demais |
| `meta` | objeto | ex.: `{"order_id": "..."}`; sem dados pessoais |
| `created_at` | datetime | **TTL** 90 dias |

## 9. Fora do contrato (decisão consciente)

Recuperação de senha esquecida, troca de e-mail, avaliações escritas pelo cliente, cupons (`discount_cents` fica 0), nota fiscal, endpoints de admin da loja (telas admin com PII mascarada ficam no E6), e views `shop_view_*` do agente (E7). Nenhuma rota da loja expõe dados do Olist original além de `shop_products`.


## Erros globais

- 422 de validação traz só `type`, `loc` e `msg` (sem `input`: PAN/CVV nunca voltam na resposta).
- Falha do MongoDB em rotas `/shop` responde 503 `{"detail": "Serviço indisponível. Tente novamente."}`.


## Views do agente (cancelamentos)

Snapshot DuckDB, sem PII. Receita de verdade = `paid`, `shipped`, `delivered` (cancelado, mesmo se já pago, não entra).

| View | Colunas novas | Observação |
|---|---|---|
| `shop_orders_view` | `canceled_date` (DATE), `cancel_reason`, `canceled_from_status` (`created`/`refused`/`paid`), `refund_cents` (BIGINT) | NULL em pedidos não cancelados e em legados |
| `shop_payments_view` | `refund_cents` | valor reembolsado; `status` do pagamento segue `approved` |
| `shop_order_items_view` | (nenhuma) | itens de pedidos de qualquer status: junte com `shop_orders_view` por `order_id` e filtre `status = 'canceled'` |

Cancelados históricos do Olist: `orders.order_status = 'canceled'` (e `order_items`).
