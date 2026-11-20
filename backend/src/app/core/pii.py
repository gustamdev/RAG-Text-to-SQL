"""Filtro de PII para texto que vai ao LLM, ao log e à memória de sessão: e-mail e CEP completo."""

import re
from typing import Any

REDACTED = "[redigido]"
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# shortcut: qualquer número de 8 dígitos em texto também é mascarado
_CEP = re.compile(r"(?<![0-9])[0-9]{5}-?[0-9]{3}(?![0-9])")


def redact(text: str) -> str:
    return _CEP.sub(REDACTED, _EMAIL.sub(REDACTED, text))


def redact_value(value: Any) -> Any:
    return redact(value) if isinstance(value, str) else value
