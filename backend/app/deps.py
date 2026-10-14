"""Request dependencies: authenticated caller, role checks and rate limits."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app import rate_limit
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.errors import ApiError
from app.security import decode_access_token


@dataclass(frozen=True)
class Caller:
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    locale: str


def get_caller(request: Request, db: Session = Depends(get_db)) -> Caller:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "unauthorized", "Authentication required.")
    try:
        data = decode_access_token(header[7:].strip())
        user_id = uuid.UUID(data["sub"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "token-expired", "Session expired, please sign in again.") from None
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise ApiError(401, "unauthorized", "Invalid token.") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active or str(user.organization_id) != data.get("org"):
        raise ApiError(401, "unauthorized", "Inactive or unknown account.")
    request.state.user_id = str(user.id)
    return Caller(user.id, user.organization_id, user.role, user.locale)


def require_admin(caller: Caller = Depends(get_caller)) -> Caller:
    if caller.role != "admin":
        raise ApiError(403, "forbidden", "Administrator role required.")
    return caller


def limit_auth(request: Request) -> None:
    rate_limit.check(f"auth:{rate_limit.client_ip(request)}", get_settings().rate_auth_per_minute, 60)


def limit_refresh(request: Request) -> None:
    rate_limit.check(f"refresh:{rate_limit.client_ip(request)}", get_settings().rate_refresh_per_minute, 60)


def limit_compute(caller: Caller = Depends(get_caller)) -> Caller:
    rate_limit.check(f"compute:{caller.user_id}", get_settings().rate_compute_per_hour, 3600)
    return caller


def limit_explain(caller: Caller = Depends(get_caller)) -> Caller:
    rate_limit.check(f"explain:{caller.user_id}", get_settings().rate_explain_per_hour, 3600)
    return caller
