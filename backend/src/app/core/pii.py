"""Filtro de PII para texto que vai ao LLM, ao log e à memória de sessão: e-mail e CEP completo."""

import re
from typing import Any

REDACTED = "[redigido]"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CEP = re.compile(r"(?<!\d)\d{5}-?\d{3}(?!\d)")  # shortcut: qualquer número de 8 dígitos em texto também é mascarado


def redact(text: str) -> str:
    return _CEP.sub(REDACTED, _EMAIL.sub(REDACTED, text))


def redact_value(value: Any) -> Any:
    return redact(value) if isinstance(value, str) else value
