# Backend — Olist Insights

API FastAPI em camadas (`src/app`): rotas → schemas → services → database. Agente Text-to-SQL em LangGraph, análise de produtos sobre DuckDB e login de administrador com JWT.

Guia completo de uso, arquitetura e decisões: [README da raiz](../README.md). Mapa de todas as rotas: [docs/MAPA_DA_API.md](docs/MAPA_DA_API.md).

```bash
cp .env.example .env     # preencha OPENAI_API_KEY (e JWT_SECRET em produção)
uv sync
uv run python run.py     # sobe o Mongo via docker compose, faz o seed e gera o snapshot DuckDB
uv run python scripts/create_admin.py voce@email.com "Seu Nome"
uv run ruff check . && uv run ruff format --check . && uv run pytest
```
