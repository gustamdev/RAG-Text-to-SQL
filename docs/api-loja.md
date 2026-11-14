# API da loja simulada: contrato (E1 a E6)

Contrato único para frontend e agentes de backend. Deriva de `docs/plano-loja-simulada.md` (v2) e `docs/loja-ux.md`. Nada aqui está implementado ainda, exceto a fundação (E0): tokens com `aud`, `POST /api/v1/auth/logout` do admin, índices e routers vazios. Onde o plano deixa decisão pendente do dono, está marcado **(pendente)**.

## 1. Convenções gerais

- Base: `/api/v1`. Os routers já existem, vazios, em `backend/src/app/api/routes/shop_*.py`, com prefixos `/shop/auth`, `/shop/products`, `/shop/cart`, `/shop/checkout`, `/shop/account`.
- JSON em UTF-8. Datas em ISO 8601 UTC (`2026-11-13T18:20:00Z`). **Dinheiro sempre em inteiros de centavos de BRL** (`*_cents`), nunca float. Peso em gramas (`weight_g`), dimensões em cm.
- Autenticação do cliente: `Authorization: Bearer <token>` com JWT `aud=shop`. Token de admin (`aud=admin`) nunca vale na loja, e token da loja nunca vale no admin (chaves de assinatura distintas por audiência). Claims: `sub` (id do cliente), `aud`, `jti`, `tv` (token_version), `exp`. O servidor compara `tv` com `token_version` do cliente a cada requisição; diferente = 401. Logout e exclusão de conta incrementam `token_version`.
- Rotas marcadas **público** não exigem token, mas passam pelo limitador por IP (`enforce_public_rate_limit`).
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
  "created_at": "2026-11-13T18:20:00Z" }

// OrderSummary (listas)
{ "order_id": "...", "state": "shipped", "total_cents": 22970, "item_count": 3, "created_at": "..." }
```

Estados do pedido: `created`, `paid`, `refused`, `shipped`, `delivered`, `canceled`. Transições válidas (o servidor valida; o cliente nunca define estado):

```
created -> paid | refused | canceled
refused -> paid | canceled
paid    -> shipped | canceled
shipped -> delivered
```

`shipped` e `delivered` avançam por simulação interna do servidor (sem endpoint). Pedido em `created`/`refused` com `reservation_expires_at` vencido vira `canceled` e devolve o estoque. Mensagem de transição inválida: 409 `"Esta ação não é permitida para o estado atual do pedido."`.

## 3. shop/auth

Fluxos: cadastro = `signup` + `verify-otp`; login = `login` + `login/verify-otp` (MFA por e-mail a cada login; "confiar neste dispositivo" **adiado**: não implementado, `device_token`/`trust_device` fora do contrato). OTP: 6 dígitos, HMAC com pepper, expira em `OTP_TTL_S` (300 s), `OTP_MAX_ATTEMPTS` (5) tentativas, novo OTP invalida o anterior, descartado ao usar. Envio: cooldown `OTP_RESEND_COOLDOWN_S` (60 s), máx. `OTP_MAX_SENDS_PER_HOUR` (3) por e-mail e limite por IP, persistidos no Mongo. `MAIL_BACKEND=console` imprime o código no log do servidor (proibido em prod).

### POST /shop/auth/signup (público)

Body: `{"nickname": "Ana" (opcional, 1-40), "email": "ana@exemplo.com", "password": "min 12, max 128", "accept_terms": true, "accept_adult": true, "terms_version": "1"}`.
`accept_terms` e `accept_adult` precisam ser `true`; `terms_version` precisa ser a vigente.
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
Erros: 401 `"E-mail ou senha incorretos."` (igual para e-mail inexistente, senha errada, conta não verificada ou excluída), 429 (bloqueio por tentativas, com atraso progressivo por e-mail).

### POST /shop/auth/login/verify-otp (público)

Body: `{"email": "...", "code": "123456"}`.
Resposta 200: `{"access_token": "...", "token_type": "bearer", "customer": Customer}`.
Erros: 400 (mesmas mensagens de `verify-otp`), 429.

### POST /shop/auth/logout (cliente)

Sem body. Incrementa `token_version` (revoga todos os tokens do cliente). Resposta **204**. Erros: 401.

### GET /shop/auth/me (cliente)

Resposta 200: `Customer`. Erros: 401.

## 4. shop/products (público)

Todas as rotas desta seção: sem token, limitador por IP, 503 se a base estiver indisponível. A ordem das rotas no router precisa colocar `categories` e `suggest` antes de `{product_id}`.

### GET /shop/products

Query: `q` (texto, 1-80), `category`, `min_price_cents`, `max_price_cents`, `min_rating` (1 a 5), `min_reviews` (inteiro >= 1, mínimo de avaliações), `in_stock` (bool), `sort` (`best_selling` padrão | `price_asc` | `price_desc` | `rating` | `newest`), `page` (>=1), `page_size` (1-48, padrão 24).
Resposta 200: `Page<ProductCard>`. Sem resultado: `items: []`, `total: 0`. Erros: 422, 429, 503.

### GET /shop/products/categories

Resposta 200: `[{"category": "cama_mesa_banho", "label": "Cama, mesa e banho", "product_count": 1240}]`, ordenado por `product_count` decrescente.

### GET /shop/products/suggest?q=

`q` com 2 a 80 caracteres. Resposta 200: `{"products": [ProductCard] /* até 5 */, "categories": [{"category": "...", "label": "..."}] /* até 3 */}`.

### POST /shop/products/batch (público)

Para o carrinho de convidado (`localStorage`): preço e estoque atuais. Body: `{"ids": ["...", "..."]}` (1 a 50 ids). Resposta 200: `{"items": [ProductCard]}`; ids inexistentes são omitidos (sem 404). Declarar esta rota antes de `{product_id}`. Erros: 422 (mais de 50 ou lista vazia), 429, 503.

### GET /shop/products/{product_id}

Resposta 200: `ProductDetail`. Erros: 404 `"Produto não encontrado."`.

### GET /shop/products/{product_id}/freight?zip=01310100

`zip`: 8 dígitos (aceita `01310-100`; normalizado). Frete offline: haversine entre o prefixo de CEP do depósito (`SHOP_ORIGIN_ZIP_PREFIX`) e o do destino, usando a tabela `geolocation` do Olist, mais peso. Não grava CEP nem coordenadas do cliente. Limitação aceita: prefixo de CEP é impreciso (demo).
Resposta 200: `{"zip": "01310100", "options": [FreightOption, FreightOption]}`.
Erros: 404 (produto), 422 `"CEP inválido."` (formato ou prefixo sem coordenada).

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

Pagamento 100% simulado: **nenhum valor é cobrado**. Duas etapas: criar o pedido (reserva estoque) e pagar. Ambas exigem o cabeçalho `Idempotency-Key` (8 a 64 caracteres `[A-Za-z0-9_-]`, gerada pelo cliente, **uma chave diferente por operação**). Índice único `(customer_id, scope, key)` (`scope` = `checkout` | `pay`) mais hash do corpo, TTL 24 h. Repetir a mesma chave com o mesmo corpo devolve a resposta original (mesmo pedido, sem novo desconto de estoque, mesmo código HTTP). Respostas 504/timeout **não** são persistidas em `shop_idempotency`: repetir a chave reexecuta o pagamento. Mesma chave com corpo diferente: 409 `"Idempotency-Key já usada com outro conteúdo."`. Sem o cabeçalho: 422.

### POST /shop/checkout

Header: `Idempotency-Key`. Body: `{"address_id": "...", "shipping_option": "standard" | "economy"}`.
O servidor lê o carrinho, revalida preço e estoque, calcula frete pelo CEP do endereço, reserva o estoque item a item (`find_one_and_update` com `$gte`/`$inc`, sem transação), cria o pedido em `created` com `reservation_expires_at` (15 min) e esvazia o carrinho.
Resposta **201**: `Order` (`payment: null`).
Erros: 404 (endereço de outro cliente ou inexistente), 409 `"Carrinho vazio."` / `"Estoque insuficiente."` (com `"items": [{"product_id": "...", "available": 0}]` no corpo junto de `detail`, e a reserva parcial é desfeita), 422, 429.

### POST /shop/checkout/{order_id}/pay

Header: `Idempotency-Key`. Body:

```json
{ "card_number": "4111111111110001", "holder": "ANA SOUZA", "exp_month": 12, "exp_year": 2030, "cvv": "123" }
```

O `body_hash` de `pay` usa só `order_id` + últimos 4 do cartão, nunca o PAN. Só cartões de teste, pelos últimos 4 dígitos: `0001` aprova, `0002` recusa, `0003` simula timeout. Qualquer outro número: 422 `"Use um cartão de teste."` (o PAN real nunca é gravado nem logado: o servidor guarda só bandeira e últimos 4; `holder`, `cvv` e PAN completo são descartados). O valor cobrado é sempre `order.total_cents` do servidor.
Resposta 200: `{"order": Order, "payment": {"status": "approved" | "refused", "brand": "visa", "last4": "0001"}}`. A transição é uma atualização condicional (`update_one({order_id, state: {$in: ["created","refused"]}}, state="paid")`): só quem a vence aprova, então o pagamento nunca é aprovado duas vezes. Aprovado: pedido vai a `paid` e a reserva vira definitiva. Recusado: pedido vai a `refused` (pode pagar de novo ou cancelar).
Timeout (cartão 0003): **504** `{"detail": "Não conseguimos confirmar. Tente novamente."}`; o status `timeout` existe só em `shop_payments`, a Order segue `created` (sem `payment`) e a resposta não é gravada. O cliente repete (pode reusar a `Idempotency-Key`): o pagamento é reexecutado sobre o mesmo documento de `shop_payments` do pedido (um por `order_id`).
Erros: 404 (pedido de outro cliente), 409 (estado não permite pagar, ou reserva expirada: `"Reserva expirada. Refaça o pedido."`), 422, 429.

## 7. shop/account (cliente)

### Endereços (máx. `SHOP_MAX_ADDRESSES` = 3)

- `GET /shop/account/addresses` -> 200 `[Address]`.
- `POST /shop/account/addresses` -> 201 `Address`. Body: `{"label": "Casa", "recipient": "Ana Souza", "zip": "01310100", "street": "...", "number": "1000", "complement": null, "district": "...", "city": "...", "state": "SP", "is_default": false}`. `label` 1-30, `zip` 8 dígitos, `state` UF válida, demais textos até 120. Erros: 409 `"Limite de 3 endereços atingido."`, 422.
- `PATCH /shop/account/addresses/{address_id}` -> 200 `Address`. Body: qualquer subconjunto dos campos do POST. Erros: 404, 422.
- `DELETE /shop/account/addresses/{address_id}` -> **204**. Pedidos já criados mantêm sua cópia do endereço. Erros: 404.

Marcar `is_default: true` desmarca o anterior. O primeiro endereço nasce padrão.

### Pedidos

- `GET /shop/account/orders?page=1&page_size=20` (page_size 1-50) -> 200 `Page<OrderSummary>`, mais recentes primeiro, só do cliente logado.
- `GET /shop/account/orders/{order_id}` -> 200 `Order` (inclui `timeline`). Erros: 404. É também a fonte da tela de confirmação.
- `POST /shop/account/orders/{order_id}/cancel` -> 200 `Order` em `canceled`, devolve estoque. Só de `created`, `refused` e `paid`; outros estados: 409 (mensagem de transição inválida). Erros: 404.

### Perfil, exportação e exclusão (LGPD)

- `PATCH /shop/account/profile` -> 200 `Customer`. Body: `{"nickname": "Ana" | null}` (único campo corrigível; troca de e-mail fica fora deste contrato). Erros: 422.
- `GET /shop/account/export` -> 200 JSON com cabeçalho `Content-Disposition: attachment; filename="meus-dados.json"`. Corpo: `{"exported_at": "...", "customer": {...}, "addresses": [Address], "orders": [Order], "cart": Cart}` só do cliente logado (sem hash de senha, sem segredos).
- `PATCH /shop/account/password` -> **204**. Body: `{"current_password": "...", "new_password": "min 12, max 128", "code": "123456" /* só com MFA ativo */}`. Com MFA por e-mail ativo o `code` (OTP, purpose `password`) é obrigatório. Incrementa `token_version` (revoga os tokens atuais; o cliente entra de novo). Erros: 401 `"Senha incorreta."`, 400 `"Código inválido ou expirado"`, 422, 429.
- `POST /shop/account/delete` -> **204** (substitui `DELETE /shop/account`: o corpo de DELETE é mal suportado por proxies). Body: `{"password": "...", "code": "123456" /* OTP se MFA ativo */, "confirm": "EXCLUIR"}` (reautenticação mais confirmação digitada). Remove cliente, carrinho, endereços, OTPs e os registros de `shop_idempotency` do cliente; anonimiza `shop_payments.customer_id` (nulo); anonimiza os pedidos (`customer_id` nulo, endereço reduzido a prefixo de CEP de 3 dígitos, cidade e UF, sem destinatário); incrementa `token_version` (o token deixa de valer); grava auditoria sem PII. Erros: 401 (`"Senha incorreta."` ou token inválido), 400 (OTP inválido), 422 (confirmação diferente de `EXCLUIR`), 429.

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
| `purpose` | str | não | `signup`, `login`, `rate_email`, `rate_ip` |
| `code_hash` | str ou null | segredo | HMAC-SHA256 do código com `OTP_PEPPER`; nulo nos contadores |
| `attempts` | int | não | erros do OTP |
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
| `stock` | int | nunca < 0 (decremento condicional `$gte`) |
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

### shop_idempotency

| Campo | Tipo | PII | Nota |
|---|---|---|---|
| `customer_id` | str | indireto | |
| `key` | str | não | `(customer_id, scope, key)` **único** |
| `scope` | str | não | `checkout` ou `pay` |
| `body_hash` | str | não | SHA-256 do corpo normalizado |
| `status_code`, `response` | int, objeto | **sim** | resposta guardada contém endereço; some em 24 h |
| `created_at` | datetime | não | **TTL** 24 h |

### shop_audit

Sem PII: a identidade é pseudonimizada com HMAC (`PSEUDONYM_KEY`), nunca e-mail, IP ou id em claro.

| Campo | Tipo | Nota |
|---|---|---|
| `_id` | str | |
| `event` | str | `signup, otp_sent, login_ok, login_fail, logout, order_created, order_paid, order_canceled, export, account_deleted` |
| `actor` | str | HMAC do `customer_id` (ou do e-mail em falhas de login) |
| `ip_hmac` | str | HMAC do IP |
| `meta` | objeto | ex.: `{"order_id": "..."}`; sem dados pessoais |
| `created_at` | datetime | **TTL** 90 dias |

## 9. Fora do contrato (decisão consciente)

Recuperação de senha esquecida, troca de e-mail, avaliações escritas pelo cliente, cupons (`discount_cents` fica 0), nota fiscal, endpoints de admin da loja (telas admin com PII mascarada ficam no E6), e views `shop_view_*` do agente (E7). Nenhuma rota da loja expõe dados do Olist original além de `shop_products`.
