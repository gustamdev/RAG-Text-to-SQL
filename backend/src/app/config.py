import logging
import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Caminho absoluto: com reload, o worker do uvicorn importa app.main sem passar
# pelo run.py, e o cwd nem sempre é a raiz do backend.
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
_ENV_FILE = BACKEND_DIR / ".env.local" if (BACKEND_DIR / ".env.local").exists() else BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    ENV: Literal["local", "dev", "prod"] = "local"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_EXTRA_ORIGINS: str = ""

    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "olist"
    MONGO_AUTOSTART: bool = True

    # Autenticação (JWT HS256). Em prod o segredo é obrigatório; fora dele, se vazio, um
    # segredo efêmero é gerado a cada start (os tokens deixam de valer ao reiniciar).
    JWT_SECRET: SecretStr = SecretStr("")
    JWT_EXPIRE_MINUTES: int = 60 * 12
    LOGIN_MAX_FAILURES: int = 5
    # Por e-mail (qualquer IP): após N tentativas na janela, cada nova espera 1s, 2s, 4s... até o teto.
    # Freia força bruta distribuída sem trancar o admin legítimo.
    LOGIN_FREE_ATTEMPTS_PER_EMAIL: int = 5
    LOGIN_MAX_DELAY_S: float = 10
    LOGIN_WINDOW_S: float = 900

    OLIST_BASE_URL: str = "https://raw.githubusercontent.com/gustamdev/Olist-E-Commerce-Public-Dataset-2017-2018/main"
    # Ano dos pedidos que o seed carrega no Mongo. Vazio (SEED_YEAR=) = todos os anos.
    # Mudar o valor só tem efeito num banco ainda vazio: o seed não roda sobre dados existentes.
    SEED_YEAR: int | None = None

    # Vazio = BACKEND_DIR/data/olist.duckdb
    DUCKDB_PATH: str = ""
    # Blob storage local das imagens de produto (services/blobstore.py). Vazio = BACKEND_DIR/data/blobstore.
    BLOBSTORE_DIR: str = ""
    MEDIA_BASE_URL: str = "/media"
    SQL_QUERY_TIMEOUT_S: float = 15
    SNAPSHOT_DEBOUNCE_S: float = 3  # espera antes de reconstruir o snapshot do agente após um pedido pago
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
    # Limite de perguntas ao chat por administrador (janela deslizante em memória, por processo).
    ADMIN_SHOP_RATE_LIMIT: int = 60  # consultas /admin/shop por admin na janela
    ADMIN_SHOP_RATE_WINDOW_S: float = 60
    CHAT_RATE_LIMIT: int = 20
    # Vitrine pública: pedidos por IP e janela (s). Cada consulta recalcula agregações no DuckDB.
    PUBLIC_RATE_LIMIT: int = 120
    PUBLIC_RATE_WINDOW_S: float = 60
    CHAT_RATE_WINDOW_S: float = 600

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
    # Perguntas e resultados SQL do agente podem trazer dado pessoal: por padrão o tracer NÃO envia
    # entradas nem saídas (só estrutura/latência). Desligar só com contrato/base legal para a transferência.
    LANGSMITH_HIDE_IO: bool = True

    # Loja simulada. Segredos vazios fora de prod viram valores efêmeros (ver _ensure_shop_secrets).
    MAIL_BACKEND: Literal["console", "smtp"] = "console"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: SecretStr = SecretStr("")
    SMTP_FROM: str = ""
    OTP_TTL_S: int = 300
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_S: int = 60
    OTP_MAX_SENDS_PER_HOUR: int = 3
    OTP_PEPPER: SecretStr = SecretStr("")
    PSEUDONYM_KEY: SecretStr = SecretStr("")
    SHOP_MAX_ADDRESSES: int = 3
    SHOP_CART_MAX_ITEMS: int = 50
    SHOP_CART_MAX_QTY: int = 10
    SHOP_CART_TTL_DAYS: int = 30
    SHOP_ORIGIN_ZIP_PREFIX: str = "01310"
    ZIP_API_ENABLED: bool = True  # CEP real via BrasilAPI/ViaCEP (servidor); False = só prefixo offline
    SHOP_FREE_STOCK_DEFAULT: int = 50
    SHOP_EXPIRE_INTERVAL_S: float = 60.0
    # Retenção (LGPD arts. 15-16). Padrões são PLACEHOLDERS a validar pelo dono (ver docs/lgpd-loja.md).
    SHOP_RETENTION_INTERVAL_S: float = 86400  # frequência do job de retenção
    SHOP_RETENTION_ORDER_DAYS: int = 1825  # pedidos/pagamentos encerrados: 5 anos
    SHOP_RETENTION_INACTIVE_DAYS: int = 730  # conta sem login: anonimizada após 2 anos
    SHOP_UNVERIFIED_TTL_HOURS: int = 24  # conta sem verificação de e-mail
    # Identificação exibida no aviso de privacidade. Placeholders: trocar antes de qualquer uso real.
    SHOP_CONTROLLER_NAME: str = "[CONTROLADOR A DEFINIR] (operador desta demonstração)"
    SHOP_CONTROLLER_CONTACT: str = "[ENDERECO/CNPJ A DEFINIR]"
    SHOP_DPO_NAME: str = "[ENCARREGADO A DESIGNAR]"
    SHOP_DPO_EMAIL: str = "[EMAIL-DO-ENCARREGADO A DEFINIR]"
    # Nº de workers do servidor: segredos efêmeros diferem por processo e quebram OTP/pseudônimos.
    WEB_CONCURRENCY: int = 1

    @field_validator("SEED_YEAR", mode="before")
    @classmethod
    def _empty_seed_year_means_all(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def _ensure_jwt_secret(self) -> "Settings":
        secret = self.JWT_SECRET.get_secret_value()
        if secret:
            if self.ENV == "prod" and len(secret) < 32:
                raise ValueError("JWT_SECRET precisa ter ao menos 32 caracteres quando ENV=prod.")
            return self
        if self.ENV == "prod":
            raise ValueError("JWT_SECRET é obrigatório quando ENV=prod.")
        logging.getLogger(__name__).warning("JWT_SECRET vazio: usando segredo efêmero (tokens expiram no restart).")
        self.JWT_SECRET = SecretStr(secrets.token_urlsafe(48))
        return self

    @model_validator(mode="after")
    def _ensure_shop_secrets(self) -> "Settings":
        if self.ENV == "prod" and self.MAIL_BACKEND == "console":
            raise ValueError("MAIL_BACKEND=console não é permitido quando ENV=prod (use smtp).")
        if self.MAIL_BACKEND == "smtp":
            missing = [n for n in ("SMTP_HOST", "SMTP_FROM", "SMTP_USER") if not getattr(self, n).strip()]
            if missing:
                raise ValueError(f"MAIL_BACKEND=smtp exige {', '.join(missing)}.")
        for name in ("OTP_PEPPER", "PSEUDONYM_KEY"):
            value = getattr(self, name).get_secret_value()
            if self.ENV == "prod":
                if len(value) < 32:
                    raise ValueError(f"{name} é obrigatório com ao menos 32 caracteres quando ENV=prod.")
            elif not value:
                logging.getLogger(__name__).warning("%s vazio: usando valor efêmero (muda a cada restart).", name)
                if self.WEB_CONCURRENCY > 1:
                    logging.getLogger(__name__).warning(
                        "%s efêmero com WEB_CONCURRENCY=%d: cada worker terá um valor diferente.",
                        name,
                        self.WEB_CONCURRENCY,
                    )
                setattr(self, name, SecretStr(secrets.token_urlsafe(48)))
        return self

    @property
    def duckdb_path(self) -> Path:
        return Path(self.DUCKDB_PATH) if self.DUCKDB_PATH else BACKEND_DIR / "data" / "olist.duckdb"

    @property
    def blobstore_dir(self) -> Path:
        return Path(self.BLOBSTORE_DIR) if self.BLOBSTORE_DIR else BACKEND_DIR / "data" / "blobstore"

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
    # langsmith.Client lê estas variáveis e troca inputs/outputs de cada run por {} antes do envio.
    os.environ["LANGSMITH_HIDE_INPUTS"] = os.environ["LANGSMITH_HIDE_OUTPUTS"] = (
        "true" if settings.LANGSMITH_HIDE_IO else "false"
    )
