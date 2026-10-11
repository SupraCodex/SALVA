"""Wave 2: Argon2id password hashing and short-lived JWT (HttpOnly cookie or Bearer header)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.config import get_settings

COOKIE_NAME = "salva_access"
_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerificationError, ValueError):
        return False


DUMMY_HASH = hash_password("timing-equalizer")


def create_token(user_id: int, org_id: int, role: str) -> tuple[str, int]:
    s = get_settings()
    now = datetime.now(UTC)
    ttl = s.access_token_minutes * 60
    token = jwt.encode({"sub": str(user_id), "org": org_id, "role": role, "iat": now,
                        "exp": now + timedelta(seconds=ttl)}, s.jwt_secret, algorithm="HS256")
    return token, ttl


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
