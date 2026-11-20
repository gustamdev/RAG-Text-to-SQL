# Plano: loja simulada + assistente no frontend admin (v2)

Status: v2 (histórico: a loja já foi implementada), consolidado após revisão de `critico`, `cyber` (STRIDE, 32 ameaças) e `lgpd`. Nada é implementado, commitado nem publicado. Qualquer deploy, push ou envio real de e-mail exige autorização explícita do dono.

## Objetivo e métrica de sucesso

Mostrar o agente de dados sobre dados que mudam. Critério único de sucesso, mensurável: criar conta na loja, comprar um produto, e em até 30 s o admin pergunta ao assistente "qual foi o último pedido?" e a resposta traz aquele pedido (valor, status, UF), sem nenhum dado pessoal do cliente. Pagamento 100% simulado. MFA por e-mail. Frete por localização. Assistente num frontend admin separado.

## Fatos verificados no código (arquivo:linha)

- Snapshot DuckDB: `database/sql_engine.py:47-69` (já grava `.tmp` e troca com `os.replace`), roda só no start (`main.py:33-43`). Reabrir o motor derruba consultas em voo (`sql_engine.py:84-97`); `build_snapshot` carrega a coleção inteira em memória (`:62`).
- O catálogo do agente amostra o Mongo bruto, não o DuckDB: `prompts.py:785-798` (`$sample`), chamado em `services/catalog.py:67`. Qualquer coleção `shop_*` em `known_tables` expõe PII ao LLM. A projeção sem PII só funciona se o catálogo e o `sample_table` lerem de views projetadas.
- `Role` só tem `ADMIN` (`schemas/common.py:4-7`); `UserOut.role: Role` quebra com papel novo.
- Token sem `aud` nem `jti`, segredo único (`auth/security.py:30-48`); `deps.py:95-108` busca `sub` só em `users`.
- Limitador em memória evictável (`core/rate_limit.py`), `--forwarded-allow-ips "*"` (`Dockerfile:54`), CORS só GET/POST (`main.py:115`), Mongo sem auth em `127.0.0.1:27017` (`docker-compose.yml`).
- Frontend: um app Vite, chave `olist.token` (`services/http.ts:4`), login só admin (`AuthProvider.tsx:27,51`), link da vitrine para `/backoffice` (`PublicLayout.tsx:21`).

## Decisões (v2)

D1. Coleções `shop_*` separadas das tabelas Olist: `shop_customers`, `shop_products`, `shop_carts`, `shop_addresses`, `shop_orders`, `shop_payments`, `shop_otp`, `shop_audit`. Proibido join `shop_*` x `customers` do Olist.
D2. Cliente fora de `users`. Tokens com `aud=shop` / `aud=admin` obrigatório em cada dependência, `jti` + `token_version` para revogação, segredo ou `kid` separado por audiência. Token sem `aud` é rejeitado.
D3. Frete offline por localização: haversine entre CEP-prefixo do depósito e do cliente (tabela `geolocation` do Olist) + peso do produto. Sem API externa. Sem guardar lat/lng do cliente. Limitação aceita e documentada: prefixo de CEP é impreciso (demo).
D4. Pagamento fake: só cartões de teste (0002 recusa, 0003 timeout). PAN real é descartado no servidor, nunca logado nem gravado. Guarda bandeira + últimos 4. `Idempotency-Key` com índice único `(customer_id, key)` + hash do corpo, TTL 24 h. Total, frete e desconto sempre recalculados no servidor. Aviso "pagamento simulado" na tela.
D5. Estoque sem transação (Mongo standalone): `find_one_and_update` com `$gte`/`$inc` por item, reserva com TTL e reconciliação de reservas órfãs. Estados: criado, pago, recusado, enviado, entregue, cancelado, com transições validadas no servidor (cliente nunca define estado).
D6. MFA por e-mail: OTP 6 dígitos, HMAC com pepper, índice TTL 5 min + checagem de `expires_at` no código, 5 tentativas, novo OTP invalida o anterior, comparação em tempo constante, descarte ao usar. Limites de envio por e-mail (3/h), por IP e cooldown 60 s, persistidos no Mongo (`$inc` atômico), não em memória. `MAIL_BACKEND=console|smtp`; padrão `console`; startup falha se `ENV=prod` com `console`. Senha SMTP (senha de app do Google) em `SecretStr`, fora do git e de logs. Anti-injeção de cabeçalho (CRLF). Resposta de cadastro idêntica para e-mail novo ou existente. Escopo: cliente (cadastro e login) e admin. DECISÃO PENDENTE DO DONO (ver abaixo).
D7. Agente com dados vivos, caminho simples: rebuild do snapshot sob demanda, com lock único, leitura em lotes, troca atômica e drenagem do motor antigo; chamado após cada pedido pago (debounce) e por refresh manual do admin. Sem job periódico. Tabelas do agente são views projetadas `shop_view_*`: allowlist de colunas, sem nome, e-mail, endereço, telefone nem texto livre; pseudônimo do cliente por HMAC com chave secreta; data no dia; CEP prefixo 3 dígitos. `sample_table` passa a amostrar o DuckDB projetado (não o Mongo). `CatalogService` aceita tabelas novas. Snapshot é dado pseudonimizado, tratado como dado pessoal.
D8. Dois frontends de verdade (decisão do dono, substitui o Vite multi-página sugerido antes): `frontend/` passa a ser SÓ a loja; `frontend-admin/` é um projeto Vite separado com backoffice + assistente. O admin reaproveita `components/ui` e `lib` da loja por alias de caminho (sem duplicar código), mas nenhum código de admin entra no bundle da loja. nginx: loja em 8080, admin em 8081 (outro `server`), ambos com `/api` same-origin, CSP por server block, chaves de `localStorage` distintas. Backoffice oculto: nenhum link, rota, texto ou redirect da loja aponta para ele; `noindex` + `robots.txt` Disallow no admin; em produção o admin fica em host/porta interna ou atrás de allowlist de IP/VPN no nginx. Ocultar não é controle de segurança: a autenticação (`aud=admin`, MFA) continua obrigatória. Admin sem analytics e sem fontes externas.
D9. Privacidade desde o desenho: campos mínimos (apelido/nome opcional, e-mail, CEP, cidade/UF), sem CPF, telefone nem data de nascimento, sem IP persistido (rate limit com HMAC/truncado e TTL), logs sem PII. Esqueleto de exportar/corrigir/apagar e `deleted_at` no modelo já em E1. LangSmith desligado por padrão. Aviso 18+. Dados de teste fictícios.

## Esteira (ordem revisada)

Ordem: E0 -> E8 (entrega valor sozinha) -> E1 -> (E2, E4 em paralelo) -> E3 -> E5 -> (E6, E7, E9 em paralelo) -> E10. Paralelo só com arquivos disjuntos. Esforço: S (~0,5 dia), M (~1-2 dias), L (~3+ dias).

| Etapa | Entrega | Agente | Esf. | Pronto quando (testes nomeados) | Portão |
|---|---|---|---|---|---|
| E0 Fundação e endurecimento | `Role.CUSTOMER`; `aud`/`jti`/`token_version`; `forwarded-allow-ips` restrito ao nginx; Mongo com usuário de app (privilégio mínimo); CORS com PATCH/DELETE e origens exatas; coleções+índices; config de e-mail com guarda de prod; filtro de log sem PII | backend, devops (plano) | M | `test_token_without_aud_rejected`, `test_shop_token_on_admin_401`, admin ainda loga, 33+ testes atuais verdes | cyber |
| E8 Frontend admin separado | cria `frontend-admin/` (projeto Vite próprio), move backoffice + assistente para lá, remove da loja TODA referência ao backoffice (rotas `/backoffice`, link em `PublicLayout.tsx:21`, redirect `/assistente`), nginx 8081 com `noindex` e allowlist opcional | frontend, devops (plano) | M | `grep -ri backoffice frontend/src` vazio; bundle da loja sem código de admin; 2 builds independentes; sessões isoladas (token de um app não vale no outro); assistente funciona em 8081 | reviewer + cyber |
| E1 Identidade do cliente | cadastro, OTP, login + MFA, `/shop/auth/me`, revogação, senha >= 12 + `max_length`, semáforo de argon2, política e termos antes do cadastro com aceite versionado, esqueleto DSAR, auditoria nasce aqui | backend | L | `test_otp_5_wrong_invalidates`, `test_otp_reuse_rejected`, `test_signup_no_email_enumeration`, `test_otp_limits_survive_10k_keys_flood`, `test_mail_console_in_prod_fails_startup` | cyber + lgpd |
| E2 Catálogo e estoque | `shop_products` semeado (preço = mediana de `order_items.price`, estoque inicial fixo), busca/filtros | backend, database | S | `test_seed_prices_positive_stock_nonneg` | reviewer |
| E4 Endereço e frete | endereço (máx. 3), validação de CEP, frete + prazo por distância e peso | backend, database | M | `test_freight_fixed_zips` (3 pares de CEP com valor esperado), `test_address_limit` | critico |
| E3 Carrinho | carrinho no servidor, limite de itens e quantidade, TTL 30 dias, revalida preço/estoque | backend | S | `test_cart_total_server_side`, `test_cart_item_limit` | reviewer |
| E5 Checkout e pagamento simulado | pedido, estados, reserva de estoque, gateway fake, idempotência, auditoria de compra | backend | L | `test_50_concurrent_last_item_one_wins` (estoque nunca < 0), `test_idempotent_replay_one_order_one_decrement`, `test_client_cannot_set_state_or_price`, `test_real_pan_discarded` | critico + cyber |
| E6 Pedidos, conta e DSAR | histórico do cliente, exportar (JSON), corrigir, excluir conta (reautenticação, anonimiza pedido, remove vínculo), telas admin com nome/e-mail mascarados e log de acesso | backend, frontend | M | `test_idor_cart_order_address_404` (A em recurso de B: GET/PATCH/DELETE), `test_delete_account_anonymizes_orders`, `test_export_contains_own_data_only` | cyber + lgpd |
| E7 Agente com dados vivos | views `shop_view_*`, `sample_table` no DuckDB projetado, rebuild sob demanda com lock e troca atômica, refresh após apagamento, `CatalogService` com tabelas novas, prompts/metadados, filtro de e-mail/CEP em perguntas e saídas, golden dataset de ~5 perguntas, RIPD enxuto | ia, database | L | `test_snapshot_schema_has_no_pii_columns`, `test_catalog_prompt_has_no_customer_text` (inserir nome de cliente e checar o prompt), `test_new_order_visible_to_agent_within_30s`, `test_deleted_customer_absent_from_agent`, `test_concurrent_rebuild_single_flight` | cyber + critico + lgpd |
| E9 Loja (UI) com cara de e-commerce | spec em `docs/loja-ux.md` (agente `design`). Home com banner/destaques e vitrines por categoria, menu de categorias, busca com sugestões, listagem com filtros/ordenação, página de produto (galeria, preço, frete por CEP, avaliações do Olist, estoque), carrinho em gaveta, checkout em etapas (endereço, frete, pagamento simulado, revisão), confirmação de pedido, "Minha conta" (pedidos, endereços, MFA, exportar/excluir), política/termos, aviso de demo; mobile-first; a11y básica; fontes self-host | frontend, design | L | fluxo ponta a ponta no navegador (cadastro, OTP console, compra, pedido na lista); axe sem erro crítico | qa |
| E10 Fechamento | auditoria mínima de login/compra (90 dias), job de retenção (OTP, carrinho, contas inativas), headers e plano de TLS/HSTS, docs, CI, ROPA/RIPD finais, reteste de apagamento ponta a ponta | docs, lgpd, devops (plano), qa | M | CI verde; checklist cyber e lgpd sem item aberto; `test_retention_job_purges` | cyber + lgpd + critico |

## Riscos por etapa (prob./impacto)

E7 alta/alta (PII ao LLM, rebuild em voo); E5 média/alta (concorrência sem transação); E1 média/alta (auth, OTP); E0 média/média (regressão de admin); demais baixo/médio.

## Ameaças do cyber que entram no plano

Antes do E0: T-02 (`aud`/`jti`), T-05 (`forwarded-allow-ips`), T-08 (Mongo auth), T-12 (console em prod). Antes do E1: T-03 (limitador persistente), T-09 (brute force OTP), T-10 (envio em massa), T-11 (enumeração). Antes do E5: T-17 (preço do cliente), T-18 (replay), T-19 (corrida), T-21/22 (gateway fake como oráculo, PAN real). Antes do E7: T-01 (catálogo no Mongo), T-24 (stored prompt injection), T-25 (PII), T-28 (rebuild). Ainda adicionar: IDOR (T-15), mass assignment com `extra="forbid"` (T-16), estados forjados (T-23), DoS de carrinho (T-27), reidentificação (T-26), bots e esgotamento de estoque por reserva sem pagamento, reset de senha, recuperação do MFA do admin, auditoria já no E1/E5.

## Decisões pendentes do dono

1. MFA do admin: `critico` quer cortar (admin único pode ser trancado e exige SMTP real); `cyber` e `lgpd` querem manter. Proposta: manter com código de recuperação impresso uma vez, com `MAIL_BACKEND=console` até autorizar SMTP.
2. MFA do cliente: a cada login ou só no cadastro (verificar e-mail)? `lgpd` recomenda só no cadastro para demo; você pediu MFA, então proponho cadastro + login com opção "confiar neste dispositivo por 30 dias".
3. Frete: haversine por CEP-prefixo (como no plano) ou tabela fixa por UF (mais simples, `critico`). Proposta: manter haversine, pois você pediu frete por localização.
4. SMTP real do Google: só mediante sua autorização e senha de app sua, nunca no repositório.

## Benchmark visual (pedido do dono, pendente para a E9)

A loja usa a Amazon (amazon.com.br) como referência de padrões de e-commerce: cabeçalho com busca e CEP de entrega, menu de departamentos, vitrines em carrosséis, grade de produtos com filtros laterais, página de produto com buy box, carrinho e checkout. Só estrutura e padrões de uso; nada de cópia de marca, imagens ou textos. A identidade visual do projeto (tipografia, cores e componentes atuais) se mantém. Ainda não foi feito: a observação do site ficou para antes de começar a E9.

## Fora de escopo

Pagamento real, CPF/documento, nota fiscal, imposto, deploy, push, publicação, e-mail de marketing.
