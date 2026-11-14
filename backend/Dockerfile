# syntax=docker/dockerfile:1

# --- Build: resolve e instala as dependências com uv (versões do uv.lock) -------------------
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Camada só de dependências: não é refeita enquanto pyproject.toml e uv.lock não mudam.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# O código entra depois; o projeto fica instalado em modo editável apontando para /app/src
# (config.py resolve data/ e .env a partir da raiz do backend, então src/ precisa ficar em /app).
COPY src ./src
COPY run.py ./
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- Runtime: mesma base, sem uv e sem cache de build, usuário sem privilégios --------------
FROM python:3.13-slim AS runtime

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app
# data/ guarda o dataset baixado e o snapshot DuckDB: monte um volume aqui para não refazer o seed.
RUN mkdir -p /app/data && chown app:app /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    MONGO_AUTOSTART=false \
    ENV=prod

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]

# Atrás do nginx (rede interna do compose, porta 8000 não publicada): confia no X-Forwarded-For
# para o limitador de login enxergar o IP real do cliente e não o do proxy. Quem pode ser
# proxy vem de FORWARDED_ALLOW_IPS (o compose define a sub-rede dele); sem a variável, só 127.0.0.1.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
