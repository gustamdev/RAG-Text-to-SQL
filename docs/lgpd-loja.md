# LGPD da loja simulada: revisão, ROPA e RIPD

> Aviso: documento técnico de apoio, não é aconselhamento jurídico. Validar com o encarregado (DPO) ou advogado antes de adotar. Itens com "(verificar)" exigem conferência no texto oficial (planalto.gov.br, gov.br/anpd). Nenhum dado pessoal real foi lido: revisão apenas de código. Banco, logs de produção, contratos e painéis de terceiros não foram inspecionados.

Escopo: `backend/src/app/services/shop_account.py`, `shop_admin.py`, `shop_legal.py`, `shop_auth_service.py`, `mail.py`, rotas `admin_shop.py` e `shop_account.py`, repositórios `shop_customers/orders/payments/audit`, `database/indexes.py`, `database/shop_views.py`, `config.py`.

## 1. O que está bom

- Exportação filtra por `customer_id`, sem hash de senha nem PAN (`shop_account.py:54-69`).
- Exclusão exige reautenticação, anonimiza cliente, pedidos e pagamentos, apaga endereços, carrinho e idempotência, e revoga tokens (`shop_account.py:77-92`, `shop_customers.py:45-61`).
- Backoffice devolve e-mail, telefone, nome e CEP mascarados e grava log de acesso (`shop_admin.py:14-65`).
- Auditoria só com pseudônimo HMAC e TTL de 90 dias (`shop_audit.py:12-23`, `indexes.py` linha do `shop_audit`).
- Cartão: só bandeira e last4 em `shop_payments`; cartões salvos (`shop_cards`) só por opt-in, sem PAN, CVV nem titular (ver tratamento abaixo).
- Visão do agente: pseudônimo, UF e 3 dígitos de CEP; conta apagada vira NULL (`shop_views.py:101-126`).
- TTLs: conta não verificada 24 h, OTP, carrinho 30 dias, idempotência 24 h (`indexes.py:48-66`).

## 2. Lacunas (por severidade)

### Resolvido no código (revisão posterior)

- Aviso de privacidade traz controlador e encarregado (`SHOP_CONTROLLER_*`, `SHOP_DPO_*`; os valores ainda são placeholders a preencher), finalidades e terceiros (A1, A2 e M1 em parte).
- Log de acesso admin com TTL de 365 dias, ator e IP em HMAC (M5 em parte; prazo ainda é decisão do dono).
- LangSmith com `LANGSMITH_HIDE_IO=True` por padrão e desligado por padrão (A3).
- Retenção implementada: contas não verificadas, inativas, pedidos e contas anonimizadas (M2); refresh pendente do snapshot repetido (M4).

### Alta

| # | Onde | Lacuna | Princípio/artigo |
|---|---|---|---|
| A1 | `shop_legal.py:13-14` | Aviso diz "não compartilhamos dados", mas o e-mail e o código OTP passam pelo provedor SMTP (Google, operador, possível transferência internacional) e consultas do agente vão à OpenAI e, se ligado, ao LangSmith. Texto não descreve o que o sistema faz. | Transparência (art. 6º VI, art. 9º), arts. 33-36 |
| A2 | `shop_legal.py:11-16` | Aviso sem: identificação do controlador, contato do encarregado, canal para exercer direitos sem login (conta apagada ou sem acesso), prazos de retenção por categoria, direito de peticionar à ANPD, revogação de consentimento, informação sobre compartilhamento. | Arts. 9º, 18, 41 |
| A3 | `config.py:81-84,170-177` | LangSmith: não achei `hide_inputs/hide_outputs` nem mascaramento no código. Se `LANGSMITH_TRACING` ligar, perguntas e resultados SQL do agente (pseudônimos, UF, CEP3, valores) saem para a LangChain (EUA) sem contrato nem cláusulas padrão registrados. Confirmar o que o tracer captura (verificar). | Arts. 33, 46 |

### Média

| # | Onde | Lacuna | Princípio/artigo |
|---|---|---|---|
| M1 | `shop_legal.py:13` | Base legal "execução do serviço e consentimento" misturada. Cadastro e pedido = execução de contrato (art. 7º V). O aceite de termos é obrigatório (`schemas/shop_auth.py` `accept_terms: Literal[True]`), logo não é consentimento livre. Definir base por finalidade: contrato (conta, pedido), obrigação legal (se houver nota fiscal real), legítimo interesse com LIA (segurança/auditoria, agente analítico). | Art. 7º, art. 8º |
| M2 | `indexes.py:44-66` | Sem retenção para `shop_customers` verificados, `shop_orders`, `shop_addresses`, `shop_payments`: ficam indefinidamente enquanto a conta existir. Sem rotina de inatividade. | Arts. 15-16, necessidade |
| M3 | `shop_account.py:82-87` | Anonimização deixa no cliente `created_at`, `last_login_at`, `terms_accepted_at`, `terms_version`, e o doc fica para sempre (`shop_customers.py:45-61`); pedidos e pagamentos mantêm `customer_id` e valores. Sem `customer_id` ligado a e-mail/nome o risco é baixo, mas é pseudonimização, não anonimização plena (art. 12 e 13). Registrar no aviso e definir prazo para purgar. | Art. 5º XI, art. 12 |
| M4 | `shop_account.py:89-92` | Falha no refresh do snapshot só vira log; até o próximo refresh o agente ainda vê dados do titular excluído (`shop_views.py:101` depende do refresh). Sem retry nem alerta. | Art. 18 VI, art. 6º |
| M5 | `shop_admin.py:33-34,49-50` | Log de acesso grava só `admin_id` pseudônimo e página. Falta IP/origem, termo de busca/finalidade, e a gravação ocorre após a leitura. Retenção de 90 dias (`indexes.py`, `shop_audit`) pode ser curta para trilha de acesso interno (verificar prazo aplicável, ex.: Marco Civil art. 15, 6 meses para registros de acesso de provedor de aplicação). | Art. 6º X, art. 37, art. 46 |
| M6 | `shop_account.py:54-69` | Exportação (art. 19 II: declaração completa) não traz origem dos dados, finalidade, critérios, terceiros nem retenção; é só dump. Sem reautenticação para exportar: sessão roubada vaza todo o PII do titular. | Art. 18 II e VII, art. 19 |
| M7 | `routes/shop_account.py:60-79`, `docs/api-loja.md:397` | Direitos do art. 18 faltando ou incompletos: correção só de nickname/telefone (e-mail não corrige), sem revogação de consentimento separada, sem oposição, sem revisão do agente (art. 20 não se aplica ao cliente, mas confirmar), sem canal para quem perdeu acesso. | Art. 18 |
| M8 | `mail.py:36-39` | SMTP Google: sem registro de contrato/DPA, país (EUA) e mecanismo de transferência. Corpo do e-mail é mínimo (bom). | Arts. 33-39 |
| M9 | OpenAI (`config.py:54`) | Dados enviados ao modelo não estão catalogados no aviso. Hoje são pseudonimizados na visão (bom), mas perguntas do admin podem incluir PII digitada. Falta política de entrada e opt-out de treino (verificar termos da conta). | Arts. 6º III, 33 |

### Baixa

| # | Onde | Lacuna |
|---|---|---|
| B1 | `shop_orders.py:77`, `shop_payments.py:61` | Export corta silenciosamente em 10 000 itens. |
| B2 | `shop_orders.py:82-85` | Anonimização de pedido apaga endereço mas mantém `address.state` (UF); aceitável, documentar. |
| B3 | `shop_admin.py:55` | Lista admin expõe `customer_id` e flag `deleted`; id opaco, mas permite cruzar telas. Mascarar ou usar pseudônimo. |
| B4 | `shop_admin.py:14-23` | Máscara de e-mail mantém 1ª letra e domínio inteiro; de telefone revela 2 últimos dígitos. Adequado para o fim, revisar se admin não precisa do dado. |
| B5 | `shop_account.py:82-87` | Pedidos `created/refused` abertos não são cancelados na exclusão (reserva de estoque até expirar). |
| B6 | `shop_legal.py:9` | "18 anos ou mais" por autodeclaração (`accept_adult`); suficiente para demo, registrar que não há verificação. |
| B7 | `shop_audit.py:12-23` | Pseudônimo HMAC estável: enquanto `PSEUDONYM_KEY` existir, `pseudo(customer_id)` é reversível por quem tem a chave e o id. Rotacionar/descartar chave no fim da retenção. |

## 3. Ações recomendadas (ordem)

1. Reescrever `PRIVACY` (`shop_legal.py`): controlador, encarregado, canal DSAR por e-mail, finalidades com base, lista de terceiros (SMTP Google, OpenAI, LangSmith), transferência internacional, retenção por categoria, direitos completos, ANPD. Subir `TERMS_VERSION` para forçar novo aceite.
2. Aplicar `hide_inputs/hide_outputs` ou manter LangSmith desligado em produção até haver contrato e mascaramento.
3. Definir e implementar retenção (inatividade da conta, purga de contas anonimizadas, pedidos conforme finalidade).
4. Reforçar log de acesso do admin (IP pseudônimo, finalidade, gravar antes de ler) e decidir prazo.
5. Reauth no export; incluir metadados art. 19 na resposta; retry do refresh do snapshot.
6. Formalizar canal DSAR para titulares sem login, com prazos (art. 19: imediato simplificado, 15 dias completo).

## 4. ROPA resumido

| Tratamento | Dados | Titular | Finalidade | Base legal (proposta) | Onde | Acesso | Terceiros | Retenção atual |
|---|---|---|---|---|---|---|---|---|
| Cadastro/login | e-mail, apelido, telefone (opcional), hash argon2, aceite de termos, último login | cliente | Operar a conta | Contrato, art. 7º V | `shop_customers` | cliente, sistema | SMTP Google (e-mail+OTP) | Enquanto a conta existir; não verificada 24 h; anonimizada fica sem prazo |
| OTP | e-mail, hash do código | cliente | Verificar e-mail/MFA | Contrato; segurança (LIA) | `shop_otp` | sistema | SMTP Google | TTL `OTP_TTL_S` (300 s) |
| Endereços | destinatário, CEP, rua, número, bairro, cidade, UF | cliente | Entrega | Contrato | `shop_addresses` | cliente | nenhum | Até exclusão da conta |
| Consulta de CEP | CEP (8 dígitos), sem identificar o cliente | cliente (checkout) | Autopreencher endereço e calcular frete | Contrato (art. 7º V) | servidor -> BrasilAPI / ViaCEP (cache em memória, 7 dias) | sistema | BrasilAPI e ViaCEP (terceiros independentes, não operadores: não tratam dado pessoal em nome da loja; o IP de saída é do servidor, não do cliente; sem contrato, verificar termos e localização). CEP isolado, sem vínculo ao titular, em regra não é dado pessoal (art. 5º I); se for tratado junto a conta/endereço, vale a base ao lado. Listado no aviso por transparência (art. 9º), sem exigir novo aceite | Só cache em memória; CEP completo não logado |
| Pedidos | itens, valores, endereço copiado, timeline | cliente | Execução do pedido, histórico | Contrato; obrigação legal se fiscal real (verificar) | `shop_orders` | cliente; admin (mascarado) | nenhum | Sem prazo; endereço apagado na exclusão |
| Pagamento simulado | bandeira, last4, status, valor | cliente | Registrar pagamento | Contrato | `shop_payments` | cliente | gateway simulado | Sem prazo; brand/last4 apagados na exclusão |
| Cartões salvos | bandeira, last4, validade, impressão digital (HMAC do PAN com escopo do cliente), resultado simulado | cliente | Pagar mais rápido | Consentimento (art. 7º I): `save_card` é `false` por padrão e o cliente marca para salvar; revogável excluindo o cartão | `shop_cards` | cliente (só os próprios) | gateway simulado | Até o cliente excluir o cartão ou a conta; máx. 3 por cliente; entra na exportação (id, bandeira, last4, validade, criado em) |
| Carrinho | itens | cliente | Compra | Contrato | `shop_carts` | cliente | nenhum | TTL 30 dias |
| Idempotência | chave, hash do corpo | cliente | Evitar cobrança duplicada | Legítimo interesse (segurança), LIA pendente | `shop_idempotency` | sistema | nenhum | TTL 24 h |
| Auditoria | pseudônimo, evento, IP-HMAC (eventos de risco) | cliente, admin | Segurança e prestação de contas | Legítimo interesse (art. 7º IX/10), LIA pendente | `shop_audit` | admin/segurança | nenhum | TTL 90 dias |
| Backoffice | leitura mascarada de clientes/pedidos | cliente | Suporte e gestão | Legítimo interesse, LIA pendente | via API admin | admin | nenhum | n/a (log 90 dias) |
| Agente analítico | pseudônimo, UF, CEP3, valores, datas (sem PII direta) | cliente | Análise de negócio | Legítimo interesse com minimização, LIA pendente | snapshot DuckDB | admin | OpenAI (EUA), LangSmith (EUA, opcional) | Snapshot refeito; sem prazo |

Dados sensíveis (art. 5º II): nenhum coletado. Crianças: fora do escopo (18+ autodeclarado).

## 5. RIPD curto (art. 38)

**Controlador:** a definir (operador da demo). **Encarregado:** a designar. **Natureza:** loja simulada, baixo volume, sem pagamento real, sem sensíveis. Alto risco não é evidente; RIPD por prudência, pois há IA com dados pessoais e transferência internacional.

**Fluxo:** cadastro -> OTP por SMTP -> compra simulada -> pedido/pagamento -> visão pseudonimizada -> agente (OpenAI) acessado só por admin.

| Risco ao titular | Prob. | Impacto | Medida existente | Medida pendente |
|---|---|---|---|---|
| Vazamento do banco (e-mail, endereço, telefone) | Média | Alto | hash argon2, mascaramento admin, sem PAN | criptografia em repouso (verificar infra), retenção, rotação de chaves |
| Acesso indevido do admin | Baixa | Médio | máscara, `require_admin`, log | log com origem/finalidade, revisão periódica, retenção do log |
| Reidentificação via agente/terceiros | Baixa | Médio | pseudônimo, UF, CEP3 | mascarar traces LangSmith, contrato OpenAI/Google, aviso |
| Retenção excessiva | Alta | Médio | TTL de carrinho/OTP/auditoria | prazos de conta inativa e pedidos |
| Direito não atendido (exclusão parcial) | Média | Médio | anonimização completa | retry do snapshot, canal sem login, export completo |
| Transferência internacional sem mecanismo | Média | Médio | nenhuma | registrar DPA/cláusulas-padrão ANPD (Res. CD/ANPD nº 19/2024, verificar) |

**Conclusão provisória:** risco residual médio até fechar A1-A3, M1 e M2. Revisar a cada mudança de fornecedor ou finalidade.

## 6. Fontes

- Lei 13.709/2018: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
- ANPD: https://www.gov.br/anpd
