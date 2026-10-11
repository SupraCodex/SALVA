"""Wave 2. Active only when AUTH_ENABLED=true (otherwise these routes answer 404)."""
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.deps import Caller, get_caller
from app.errors import ApiError
from app.rate_limit import limit_by_ip
from app.schemas.auth import LoginIn, MeOut, RegisterIn, TokenOut
from app.security import COOKIE_NAME
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth (wave 2)"])


def _enabled() -> None:
    if not get_settings().auth_enabled:
        raise ApiError(404, "auth-disabled", "Authentication is disabled (AUTH_ENABLED=false).")


def _cookie(resp: Response, token: str, ttl: int) -> None:
    resp.set_cookie(COOKIE_NAME, token, max_age=ttl, httponly=True, secure=get_settings().cookie_secure,
                    samesite="lax", path="/")


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(_enabled), Depends(limit_by_ip)])
def register(data: RegisterIn, response: Response, db: Session = Depends(get_db)):
    token, ttl = auth_service.register(db, data)
    _cookie(response, token, ttl)
    return TokenOut(access_token=token, expires_in=ttl)


@router.post("/login", response_model=TokenOut, dependencies=[Depends(_enabled), Depends(limit_by_ip)])
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    token, ttl = auth_service.login(db, data.email, data.password)
    _cookie(response, token, ttl)
    return TokenOut(access_token=token, expires_in=ttl)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_enabled)])
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeOut, dependencies=[Depends(_enabled)])
def me(caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    u = db.get(User, caller.user_id)
    return MeOut(id=u.id, email=u.email, role=u.role, locale=u.locale, organization_id=u.organization_id,
                 organization_name=u.organization.name)
