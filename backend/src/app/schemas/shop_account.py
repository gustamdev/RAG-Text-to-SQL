import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfilePatch(_Strict):
    nickname: str | None = Field(default=None, min_length=1, max_length=40)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("nickname")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None

    @field_validator("phone")
    @classmethod
    def _digits(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        digits = re.sub(r"\D", "", value)
        if len(digits) not in (10, 11):
            raise ValueError("Telefone deve ter DDD e 8 ou 9 dígitos.")
        return digits

    @model_validator(mode="after")
    def _not_empty(self) -> "ProfilePatch":
        if not self.model_fields_set:
            raise ValueError("Informe nickname ou phone.")
        return self


class DeleteAccountIn(_Strict):
    password: str = Field(min_length=1, max_length=128)
    confirm: Literal["EXCLUIR"]


class ProfileOut(BaseModel):
    id: str
    nickname: str | None
    email: str
    phone: str | None


ExportOut = dict[str, Any]


class LegalOut(BaseModel):
    version: str
    terms: str
    privacy: str


class AdminCustomerRow(BaseModel):
    id: str
    email: str
    phone: str | None
    nickname: str | None
    created_at: str
    deleted: bool


class AdminOrderRow(BaseModel):
    order_id: str
    customer_id: str
    state: str
    total_cents: int
    created_at: str
    recipient: str | None
    zip: str | None
    city: str | None
    state_uf: str | None


class AdminPage[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class ChangePasswordIn(_Strict):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    code: str | None = Field(default=None, max_length=16)  # legado do frontend: aceito e descartado (sem OTP)
