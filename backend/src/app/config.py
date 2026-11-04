import os
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Caminho absoluto: com reload, o worker do uvicorn importa app.main sem passar
# pelo run.py, e o cwd nem sempre é a raiz do backend.
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
_ENV_FILE = BACKEND_DIR / ".env.local" if (BACKEND_DIR / ".env.local").exists() else BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    ENV: str = "local"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_EXTRA_ORIGINS: str = ""

    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "olist"
    MONGO_AUTOSTART: bool = True

    OLIST_BASE_URL: str = (
        "https://raw.githubusercontent.com/gustamdev/Olist-E-Commerce-Public-Dataset-2017-2018/main"
    )

    # Vazio = BACKEND_DIR/data/olist.duckdb
    DUCKDB_PATH: str = ""
    SQL_QUERY_TIMEOUT_S: float = 15
    SQL_MAX_CONCURRENT: int = 4
    QUERY_RESULT_TTL_S: float = 900
    QUERY_RESULT_MAX: int = 200

    # Infra de LLM (segredo e limites): os perfis de modelo (nome, temperatura) ficam em app/llm_models.py.
    OPENAI_API_KEY: SecretStr = SecretStr("")
    LLM_TIMEOUT_S: float = 30
    LLM_MAX_RETRIES: int = 2

    # Quanto tempo e quantas execuções do agente (app/agent_graph.py) ficam guardadas em
    # memória para o GET /chat/questions/{id}/events poder ler (ver services/agent_runner.py).
    CHAT_RESULT_TTL_S: float = 900
    CHAT_RESULT_MAX: int = 200

    # Memória de sessão do agente (services/memory.py): histórico recente + resumo
    # consolidado por session_id (AskRequest.session_id), para dar continuidade entre
    # perguntas. MEMORY_TURNS_PER_CONSOLIDATION é a única fonte do "N" — nunca hardcoded
    # em outro lugar do código.
    MEMORY_TURNS_PER_CONSOLIDATION: int = 10
    MEMORY_CONTEXT_MAX_TOKENS: int = 1500
    MEMORY_SESSION_TTL_S: float = 3600
    MEMORY_SESSION_MAX: int = 500

    # Observabilidade (LangSmith): o SDK da langsmith lê essas variáveis direto de
    # os.environ, não do nosso objeto Settings — por isso são projetadas abaixo, logo após
    # a instância de Settings. Desligado por padrão: sem chave, não liga sozinho.
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: SecretStr = SecretStr("")
    LANGSMITH_PROJECT: str = "rag-backend"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"

    @property
    def duckdb_path(self) -> Path:
        return Path(self.DUCKDB_PATH) if self.DUCKDB_PATH else BACKEND_DIR / "data" / "olist.duckdb"

    @property
    def is_prod(self) -> bool:
        return self.ENV == "prod"

    @property
    def compose_file(self) -> Path:
        return PROJECT_ROOT / "docker-compose.yml"

    @property
    def dataset_dir(self) -> Path:
        return BACKEND_DIR / "data" / "olist"


settings = Settings()

if settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY.get_secret_value():
    # A partir daqui, todo Runnable do LangChain/LangGraph (prompts.py, agent_graph.py) é
    # rastreado sem mais nenhuma mudança de código. config.py é importado antes de qualquer
    # chain ser montada, então a variável já está no ambiente quando a primeira chamada sai.
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
    os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
