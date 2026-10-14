"""Password hashing (Argon2id, SEC-01), short-lived access JWT and rotating refresh tokens (SEC-02)."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from app.config import get_settings

REFRESH_COOKIE = "salva_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"
# OWASP Password Storage Cheat Sheet minimum for Argon2id: m=19 MiB, t=2, p=1.
_ARGON2 = {"length": 32, "iterations": 2, "lanes": 1, "memory_cost": 19 * 1024}


def hash_password(password: str) -> str:
    kdf = Argon2id(salt=os.urandom(16), **_ARGON2)
    return kdf.derive_phc_encoded(password.encode("utf-8"))


def verify_password(password: str, encoded: str) -> bool:
    try:
        Argon2id.verify_phc_encoded(password.encode("utf-8"), encoded)
    except (InvalidKey, ValueError, TypeError):
        return False
    return True


# Verifying against this hash when the account does not exist keeps response times similar.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def create_access_token(user_id: str, org_id: str, role: str) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = settings.access_token_minutes * 60
    payload = {
        "sub": user_id,
        "org": org_id,
        "role": role,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), ttl


def decode_access_token(token: str) -> dict:
    data = jwt.decode(
        token,
        get_settings().jwt_secret,
        algorithms=["HS256"],
        options={"require": ["exp", "iat", "sub", "org", "typ"]},
    )
    if data.get("typ") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return data


def new_refresh_token() -> tuple[str, str]:
    """Return (opaque token sent to the browser, SHA-256 hash stored in the database)."""
    token = secrets.token_urlsafe(48)
    return token, hash_refresh_token(token)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
