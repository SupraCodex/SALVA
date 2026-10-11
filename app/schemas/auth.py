from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from .common import Strict


class RegisterIn(Strict):
    organization_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    locale: Literal["fr", "en"] = "fr"


class LoginIn(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class MeOut(BaseModel):
    id: int
    email: str
    role: str
    locale: str
    organization_id: int
    organization_name: str


class OutcomeIn(Strict):
    analysis_id: int | None = None
    decision_taken: Literal["continue", "store", "reroute", "sell_local", "optimized_split", "other"]
    actual_kg: float | None = Field(None, ge=0, le=100_000)
    actual_revenue_fcfa: float | None = Field(None, ge=0)


class OutcomeOut(BaseModel):
    id: int
    lot_id: int
    analysis_id: int | None
    decision_taken: str
    followed_reco: bool | None
    actual_kg: float | None
    actual_revenue_fcfa: float | None
    recorded_at: datetime
