from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import Caller, require_admin
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.services import auth as auth_service

router = APIRouter(prefix="/admin", tags=["administration"])


@router.get("/users", response_model=list[UserOut], summary="Users of the organization")
def users(caller: Caller = Depends(require_admin), db: Session = Depends(get_db)):
    return auth_service.list_users(db, caller.organization_id)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user in the organization",
)
def create_user(
    data: UserCreate,
    caller: Caller = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return auth_service.create_user(db, caller.organization_id, caller.user_id, data)


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    summary="Change a user's role or deactivate them",
)
def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    caller: Caller = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return auth_service.update_user(db, caller.organization_id, caller.user_id, user_id, data)
