"""Perfis de modelo LLM: um por tipo de tarefa, prontos para instanciar num `PromptSpec.chain(...)`.

Cada classe fixa modelo, temperatura e teto de tokens para a tarefa que ela atende, então quem
monta uma chain não repete essas escolhas em cada lugar. Segredo e limites de infraestrutura
(API key, timeout, retries) ficam em `config.py`; aqui só entram escolhas de produto por tarefa.

    SQLModel().build()        -> ChatOpenAI para SQL_AGENT (prompts.py)
    ValidationModel().build() -> ChatOpenAI para COLUMN_METADATA, TABLE_DESCRIPTION, PROMPT_OPTIMIZER
    TextModel().build()       -> ChatOpenAI para um futuro agente de resposta em texto ao usuário
"""

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.config import settings


class LLMProfile(BaseModel):
    """Base dos perfis: cada subclasse só declara o que muda de uma tarefa para outra."""

    model: str
    temperature: float
    max_tokens: int

    def build(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=settings.LLM_TIMEOUT_S,
            max_retries=settings.LLM_MAX_RETRIES,
            api_key=settings.OPENAI_API_KEY,
        )


class TextModel(LLMProfile):
    """Barato, para texto corrido em linguagem natural (não para saída estruturada).

    gpt-4.1-nano foi desligado pela OpenAI em 23/10/2026; gpt-5.6-luna é o substituto
    oficial (nível mais barato da geração atual). https://developers.openai.com/api/docs/deprecations
    """

    model: str = "gpt-5.6-luna"
    temperature: float = 0.3
    max_tokens: int = 1024


class ValidationModel(LLMProfile):
    """Intermediário, para extração e validação de informação estruturada.

    Usa saída estruturada (`with_structured_output`), então temperatura 0: aqui o objetivo
    é consistência com o schema, não variedade de texto.
    """

    model: str = "gpt-4.1-mini"
    temperature: float = 0
    max_tokens: int = 2048


class SQLModel(LLMProfile):
    """Avançado, não fronteira: gerar SQL exige mais raciocínio do que validar metadados."""

    model: str = "gpt-4.1"
    temperature: float = 0
    max_tokens: int = 2048
