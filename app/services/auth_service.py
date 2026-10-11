"""Wave 2: register / login."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Organization, User
from app.errors import ApiError
from app.schemas.auth import RegisterIn
from app.security import DUMMY_HASH, create_token, hash_password, verify_password


def register(db: Session, data: RegisterIn) -> tuple[str, int]:
    email = data.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise ApiError(409, "email-taken", "An account already exists with this email.")
    if db.scalar(select(Organization.id).where(Organization.name == data.organization_name.strip())):
        raise ApiError(409, "organization-taken", "This organization name is already used.")
    org = Organization(name=data.organization_name.strip())
    db.add(org)
    db.flush()
    user = User(organization_id=org.id, email=email, role="admin", locale=data.locale,
                password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    return create_token(user.id, org.id, user.role)


def login(db: Session, email: str, password: str) -> tuple[str, int]:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        verify_password(password, DUMMY_HASH)  # same timing as a wrong password
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise ApiError(401, "invalid-credentials", "Wrong email or password.")
    return create_token(user.id, user.organization_id, user.role)
