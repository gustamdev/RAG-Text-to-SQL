# Segurança da loja: TLS, logs, incidentes e CI (E10)

> Documento técnico de apoio, não é aconselhamento jurídico. Itens "(decisão do dono)" precisam de escolha humana. Nada aqui habilita deploy.

## 1. Headers de segurança

O backend (`app/main.py`, middleware `security_headers`) acrescenta, se a rota não definiu: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Permissions-Policy` (câmera, microfone, geolocalização off) e `Cross-Origin-Resource-Policy: same-site`. Não define HSTS nem CSP: HSTS depende de TLS (proxy) e CSP depende do que os frontends carregam.

## 2. Plano de TLS e HSTS atrás de proxy

1. Terminar TLS no proxy (nginx, Caddy, load balancer do provedor) com certificado automático (Let's Encrypt ou gerenciado). TLS 1.2+ apenas.
2. Redirecionar HTTP para HTTPS no proxy. A API fica só na rede interna (porta do uvicorn não exposta).
3. Proxy envia `X-Forwarded-For`/`X-Forwarded-Proto`. Rodar uvicorn com `--proxy-headers --forwarded-allow-ips=<IP do proxy>` (nunca `*`; liste só o IP/CIDR do proxy reverso) e o proxy deve SOBRESCREVER `X-Forwarded-For` (não anexar ao valor do cliente): o rate limit por IP (login, catálogo, `/shop/zip`) depende disso. Sem isso, `request.client.host` (usado nos limites e na auditoria) será o IP do proxy.
4. HSTS no proxy: começar com `Strict-Transport-Security: max-age=300`, subir para 6 meses e só então `includeSubDomains`; `preload` só com decisão consciente (difícil de reverter). Só depois de confirmar que todo subdomínio atende HTTPS.
5. CORS: `CORS_EXTRA_ORIGINS` só com as origens HTTPS reais dos dois frontends. `ENV=prod` desliga `/docs` e `/openapi.json`.
6. CSP dos frontends (estáticos): definir no proxy/host estático (decisão do dono, depende dos assets).

## 3. Política de logs de acesso e IP

- Log de aplicação: sem corpo de requisição, senha, OTP, PAN, e-mail completo; a URI do Mongo é mascarada (`mask_uri`). 422 não ecoa o corpo.
- Auditoria (`shop_audit`): só pseudônimos HMAC (`PSEUDONYM_KEY`), IP só em HMAC e só nos eventos de risco e de acesso admin. Retenção 90 dias; acesso de administradores 365 dias com finalidade (`suporte`, `auditoria`, `analise`) gravada antes da leitura.
- Log de acesso do proxy (IP em claro): é dado pessoal. Proposta: 90 dias, acesso restrito, rotação automática, sem query string com dado pessoal. Prazo legal aplicável (decisão do dono; verificar Marco Civil art. 15 se a loja deixar de ser demonstração).
- Consulta de CEP (`GET /shop/zip/{cep}`, pública): o CEP vai no path. O access log do uvicorn o mascara (`MaskZipFilter`), mas o log do proxy pode guardá-lo junto ao IP do titular; a retenção de 90 dias acima cobre isso. As chamadas a BrasilAPI/ViaCEP saem do servidor, sem dado do cliente.
- Rotacionar/descartar `PSEUDONYM_KEY` ao fim da retenção do que ela protege.

Nos frontends, `frontend/nginx.conf` e `frontend-admin/nginx.conf` trazem `set_real_ip_from`/`real_ip_header` comentados: ative-os com o IP real do proxy de borda, senão todos os clientes compartilham o IP do proxy nos limites.

### Esqueci minha senha (loja)

`forgot-password` responde 202 idêntico para qualquer e-mail (anti enumeração; o envio é em segundo plano). `reset-password` só aceita OTP `reset` válido (comparação em tempo constante, uso único, 5 erros invalidam) e responde 400 genérico em qualquer falha. Sucesso: novo hash argon2, `token_version + 1` (todas as sessões caem), OTPs `login`/`reset` do e-mail apagados, contador `rate_login_email` do próprio e-mail limpo (contadores de IP e par ficam), auditoria `password_reset` sem senha nem código, aviso por e-mail. Sem login automático. Risco residual: quem controla a caixa de entrada redefine a senha (mesmo modelo de confiança do login por OTP). LGPD: o e-mail é usado só para esse envio, sem dado novo.

### Limites: Mongo x memória

- Persistidos no Mongo (`shop_otp`, valem entre réplicas e reinícios; chaves em HMAC): `rate_email`, `rate_ip` (envio de OTP), `rate_lsend_email`, `rate_lsend_ip` (envio de login), `rate_rsend_email`, `rate_rsend_ip` (envio de reset), `rate_login_email`, `rate_login_ip`, `rate_login_pair` (login da loja), `rate_delete_pw` (senha errada na exclusão).
- Em memória, por processo (zeram no reinício e não somam entre réplicas): login admin (`FailureLimiter`, `app.state.login_limiter`; tabela cheia evicta a chave mais antiga), limites por IP público/catálogo/auth da loja (`PUBLIC_RATE_LIMIT`), por cliente, escrita do checkout, chat (`CHAT_RATE_LIMIT`) e backoffice da loja (`ADMIN_SHOP_RATE_LIMIT`). Com várias réplicas, mover para Redis/Mongo.

## 4. Runbook de incidente (resumo)

1. Detectar e conter: revogar o segredo suspeito (`JWT_SECRET` invalida todos os tokens; `PSEUDONYM_KEY`/`OTP_PEPPER` com impacto em auditoria/OTP), desligar o acesso admin se preciso, preservar logs.
2. Avaliar: quais dados (e-mail, telefone, endereço, pedidos), quantos titulares, se há risco relevante.
3. Comunicar: encarregado imediatamente; se houver risco ou dano relevante, comunicar a ANPD e os titulares em prazo razoável (LGPD art. 48; prazo regulamentado pela ANPD, verificar a resolução vigente).
4. Corrigir e aprender: causa raiz, teste que reproduz, nota no registro de incidentes.
5. Registrar tudo (data, escopo, decisões). Contatos do controlador e do encarregado vêm de `SHOP_CONTROLLER_*` e `SHOP_DPO_*` (placeholders: preencher).

## 5. CI

`.github/workflows/ci.yml` roda em push na `main` e em PR, só com `contents: read` e sem passos de deploy:

- Backend: `ruff check`, `ruff format --check`, `pytest -q`.
- Loja (`frontend`): `oxlint`, `tsc -b`, `vitest run`, `npm run build`.
- Admin (`frontend-admin`): `oxlint`, `vitest run`, `npm run build`.

Pendente (decisão do dono): auditoria de dependências (`pip-audit`, `npm audit`) e fixar actions por SHA.
