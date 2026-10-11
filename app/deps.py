"""Who is calling. Wave 1: auth disabled -> the seeded 'demo' organization.
Wave 2: AUTH_ENABLED=true -> JWT from the HttpOnly cookie or the Authorization header."""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Organization, User
from app.db.session import get_db
from app.errors import ApiError
from app.security import COOKIE_NAME, decode_token

DEMO_ORG = "demo"


@dataclass(frozen=True)
class Caller:
    organization_id: int
    user_id: int | None
    role: str
    locale: str = "fr"


def _token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE_NAME)


def get_caller(request: Request, db: Session = Depends(get_db)) -> Caller:
    if not get_settings().auth_enabled:
        org = db.scalar(select(Organization).where(Organization.name == DEMO_ORG))
        if org is None:
            raise ApiError(503, "not-seeded", "Demo organization missing: run `python -m scripts.seed_demo`.")
        return Caller(org.id, None, "admin")
    token = _token(request)
    if not token:
        raise ApiError(401, "unauthorized", "Authentication required.")
    try:
        data = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "token-expired", "Session expired, please log in again.") from None
    except jwt.InvalidTokenError:
        raise ApiError(401, "unauthorized", "Invalid token.") from None
    user = db.get(User, int(data["sub"]))
    if user is None or not user.is_active:
        raise ApiError(401, "unauthorized", "Inactive or unknown account.")
    return Caller(user.organization_id, user.id, user.role, user.locale)


def require_admin(caller: Caller = Depends(get_caller)) -> Caller:
    if caller.role != "admin":
        raise ApiError(403, "forbidden", "Admin role required.")
    return caller
