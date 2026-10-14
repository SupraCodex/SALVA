"""Registration, sign-in, refresh-token rotation, sign-out and organization users."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import rate_limit
from app.config import get_settings
from app.db.models import Organization, RefreshToken, User
from app.errors import ApiError, not_found
from app.schemas.auth import MeOut, RegisterIn, UserCreate, UserUpdate
from app.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.services import audit

COMMON_PASSWORDS = frozenset(
    {
        "password123",
        "1234567890",
        "azertyuiop",
        "qwertyuiop",
        "motdepasse",
        "password1234",
        "0123456789",
    }
)
MAX_FAILED_PER_EMAIL = 5  # failed sign-ins per account before a temporary lockout (§36)
LOCKOUT_WINDOW_S = 15 * 60


def me(user: User) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        role=user.role,
        locale=user.locale,
        organization_id=user.organization_id,
        organization_name=user.organization.name,
    )


def _check_password_policy(password: str, email: str) -> None:
    if password.lower() in COMMON_PASSWORDS or password.lower() == email.split("@")[0]:
        raise ApiError(
            422,
            "validation-error",
            "One or more fields are invalid.",
            [
                {
                    "field": "password",
                    "code": "weak_password",
                    "message": "password is too common",
                }
            ],
        )


def issue_session(db: Session, user: User, family_id: uuid.UUID | None = None) -> tuple[str, int, str]:
    """Create an access token and a new refresh token in the given (or a new) family."""
    access, ttl = create_access_token(str(user.id), str(user.organization_id), user.role)
    token, digest = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id or uuid.uuid4(),
            token_hash=digest,
            expires_at=datetime.now(UTC) + timedelta(days=get_settings().refresh_token_days),
        )
    )
    return access, ttl, token


def register(db: Session, data: RegisterIn) -> tuple[User, str, int, str]:
    _check_password_policy(data.password, data.email)
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise ApiError(409, "email-taken", "An account already exists with this e-mail.")
    name = " ".join(data.organization_name.split())
    if db.scalar(select(Organization.id).where(Organization.name == name)):
        raise ApiError(409, "organization-taken", "This organization name is already used.")
    org = Organization(name=name)
    db.add(org)
    db.flush()
    # The first user of an organization becomes its administrator (§36): no default admin.
    user = User(
        organization_id=org.id,
        email=data.email,
        role="admin",
        locale=data.locale,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.flush()
    audit.record(db, "register", "user", user.id, organization_id=org.id, user_id=user.id)
    access, ttl, refresh = issue_session(db, user)
    db.commit()
    db.refresh(user)
    return user, access, ttl, refresh


def login(db: Session, email: str, password: str) -> tuple[User, str, int, str]:
    lock_key = f"login-failures:{email}"
    if rate_limit.count(lock_key, LOCKOUT_WINDOW_S) >= MAX_FAILED_PER_EMAIL:
        raise ApiError(
            429,
            "account-locked",
            "Too many failed attempts for this account, retry in a few minutes.",
            headers={"Retry-After": str(LOCKOUT_WINDOW_S)},
        )
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(password, DUMMY_HASH)  # same timing as a wrong password
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        audit.record(
            db,
            "login_failed",
            "user",
            user.id if user else None,
            organization_id=user.organization_id if user else None,
        )
        db.commit()
        rate_limit.hit(lock_key)
        raise ApiError(401, "invalid-credentials", "Wrong e-mail or password.")
    rate_limit.clear(lock_key)
    access, ttl, refresh = issue_session(db, user)
    audit.record(
        db,
        "login",
        "user",
        user.id,
        organization_id=user.organization_id,
        user_id=user.id,
    )
    db.commit()
    return user, access, ttl, refresh


def refresh(db: Session, token: str | None) -> tuple[User, str, int, str]:
    if not token:
        raise ApiError(401, "unauthorized", "No active session.")
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token)))
    now = datetime.now(UTC)
    if row is None:
        raise ApiError(401, "unauthorized", "No active session.")
    if row.revoked_at is not None:
        # A rotated token was replayed: revoke the whole family (likely theft).
        db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == row.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        audit.record(db, "refresh_reuse_detected", "user", row.user_id, user_id=row.user_id)
        db.commit()
        raise ApiError(401, "unauthorized", "Session revoked, please sign in again.")
    if row.expires_at <= now:
        raise ApiError(401, "unauthorized", "Session expired, please sign in again.")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise ApiError(401, "unauthorized", "Inactive or unknown account.")
    row.revoked_at = now
    access, ttl, new_token = issue_session(db, user, family_id=row.family_id)
    db.commit()
    return user, access, ttl, new_token


def logout(db: Session, token: str | None) -> None:
    if not token:
        return
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token)))
    if row is not None:
        db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == row.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        audit.record(db, "logout", "user", row.user_id, user_id=row.user_id)
        db.commit()


def list_users(db: Session, org_id: uuid.UUID) -> list[User]:
    return list(db.scalars(select(User).where(User.organization_id == org_id).order_by(User.created_at)))


def create_user(db: Session, org_id: uuid.UUID, actor_id: uuid.UUID, data: UserCreate) -> User:
    _check_password_policy(data.password, data.email)
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise ApiError(409, "email-taken", "An account already exists with this e-mail.")
    user = User(
        organization_id=org_id,
        email=data.email,
        role=data.role,
        locale=data.locale,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        "user_created",
        "user",
        user.id,
        organization_id=org_id,
        user_id=actor_id,
        detail={"role": data.role},
    )
    db.commit()
    return user


def update_user(
    db: Session,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    user_id: uuid.UUID,
    data: UserUpdate,
) -> User:
    user = db.scalar(select(User).where(User.id == user_id, User.organization_id == org_id))
    if user is None:
        raise not_found("User")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if user.id == actor_id and (changes.get("role") == "operator" or changes.get("is_active") is False):
        raise ApiError(409, "self-demotion", "You cannot remove your own administrator access.")
    for key, value in changes.items():
        setattr(user, key, value)
    if changes.get("is_active") is False:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
    audit.record(
        db,
        "user_updated",
        "user",
        user.id,
        organization_id=org_id,
        user_id=actor_id,
        detail={k: v for k, v in changes.items()},
    )
    db.commit()
    return user
