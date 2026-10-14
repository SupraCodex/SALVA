from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .common import Out, StrictIn, normalize_email


class RegisterIn(StrictIn):
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)
    organization_name: str = Field(min_length=2, max_length=120)
    locale: Literal["fr", "en"] = "fr"

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginIn(StrictIn):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return value.strip().lower()


class MeOut(Out):
    id: uuid.UUID
    email: str
    role: Literal["admin", "operator"]
    locale: Literal["fr", "en"]
    organization_id: uuid.UUID
    organization_name: str


class MeUpdate(StrictIn):
    locale: Literal["fr", "en"]


class TokenOut(Out):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int
    user: MeOut


class UserCreate(StrictIn):
    email: str = Field(max_length=254)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["admin", "operator"] = "operator"
    locale: Literal["fr", "en"] = "fr"

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        return normalize_email(value)


class UserUpdate(StrictIn):
    role: Literal["admin", "operator"] | None = None
    is_active: bool | None = None


class UserOut(Out):
    id: uuid.UUID
    email: str
    role: str
    locale: str
    is_active: bool
    created_at: datetime
