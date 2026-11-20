from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

TERMS_VERSION = "2"

_Code = Field(pattern=r"^[0-9]{6}$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SignupRequest(_Strict):
    nickname: str | None = Field(default=None, min_length=1, max_length=40)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    accept_terms: Literal[True]
    accept_adult: Literal[True]
    terms_version: str

    @field_validator("nickname")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None

    @field_validator("terms_version")
    @classmethod
    def _current_terms(cls, value: str) -> str:
        if value != TERMS_VERSION:
            raise ValueError("Versão dos termos desatualizada.")
        return value


class VerifyOtpRequest(_Strict):
    email: EmailStr
    code: str = _Code


class ResendOtpRequest(_Strict):
    email: EmailStr
    purpose: Literal["signup", "login"]


class ShopLoginRequest(_Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(_Strict):
    email: EmailStr


class ForgotPasswordOut(BaseModel):
    masked_email: str
    message: str


class ResetPasswordRequest(_Strict):
    email: EmailStr
    code: str = _Code
    new_password: str = Field(min_length=12, max_length=128)


class OkOut(BaseModel):
    ok: bool = True


class DetailOut(BaseModel):
    detail: str


class MfaRequiredOut(BaseModel):
    mfa_required: bool = True
    masked_email: str


class CustomerOut(BaseModel):
    id: str
    nickname: str | None
    email: str
    phone: str | None = None
    terms_version: str
    created_at: str


class ShopTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer: CustomerOut
