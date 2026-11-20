"""Contrato de cartões salvos (simulado). Nunca expõe nem guarda PAN, CVV ou titular. Ver docs/api-loja.md."""

import re
from typing import Annotated

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.schemas.shop_store import Strict


class CardIn(Strict):
    # SecretStr: repr/log mascarados. O corpo nunca é gravado; só bandeira + últimos 4 + validade saem daqui.
    card_number: SecretStr = Field(repr=False)
    holder: SecretStr = Field(min_length=1, max_length=60, repr=False)
    exp_month: Annotated[int, Field(ge=1, le=12)]
    exp_year: Annotated[int, Field(ge=2000, le=2100)]
    cvv: SecretStr = Field(repr=False)

    @field_validator("card_number", mode="before")
    @classmethod
    def _pan(cls, value):
        """Aceita espaço/hífen entre grupos; 13 a 19 dígitos."""
        digits = value.replace(" ", "").replace("-", "") if isinstance(value, str) else value
        if not isinstance(digits, str) or not re.fullmatch(r"[0-9]{13,19}", digits):
            raise ValueError("Número de cartão inválido.")  # sem ecoar o valor
        return digits

    @field_validator("cvv", mode="before")
    @classmethod
    def _cvv(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{3,4}", value):
            raise ValueError("CVV inválido.")
        return value


class CardOut(BaseModel):
    id: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int
