"""Authentication: access token in the response body (kept in memory by the client), refresh
token in an HttpOnly, SameSite=Strict cookie scoped to /api/v1/auth and rotated on every use."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User
from app.db.session import get_db
from app.deps import Caller, get_caller, limit_auth
from app.errors import ApiError
from app.schemas.auth import LoginIn, MeOut, MeUpdate, RegisterIn, TokenOut
from app.security import REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])
CSRF_HEADER = "x-requested-with"


def _set_refresh(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def _require_csrf_header(request: Request) -> None:
    # A custom header cannot be sent cross-site without a CORS preflight (defence in depth).
    if request.headers.get(CSRF_HEADER, "").lower() != "salva":
        raise ApiError(403, "csrf", "Missing X-Requested-With header.")


def _token_out(user: User, access: str, ttl: int) -> TokenOut:
    return TokenOut(access_token=access, expires_in=ttl, user=auth_service.me(user))


@router.post(
    "/auth/register",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_auth)],
    summary="Create an account and its organization",
)
def register(data: RegisterIn, response: Response, db: Session = Depends(get_db)):
    user, access, ttl, refresh = auth_service.register(db, data)
    _set_refresh(response, refresh)
    return _token_out(user, access, ttl)


@router.post(
    "/auth/login",
    response_model=TokenOut,
    dependencies=[Depends(limit_auth)],
    summary="Sign in",
)
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user, access, ttl, refresh = auth_service.login(db, data.email, data.password)
    _set_refresh(response, refresh)
    return _token_out(user, access, ttl)


@router.post(
    "/auth/refresh",
    response_model=TokenOut,
    dependencies=[Depends(limit_auth)],
    summary="Rotate the refresh cookie and return a new access token",
)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    _require_csrf_header(request)
    user, access, ttl, token = auth_service.refresh(db, request.cookies.get(REFRESH_COOKIE))
    _set_refresh(response, token)
    return _token_out(user, access, ttl)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
def logout(request: Request, db: Session = Depends(get_db)):
    _require_csrf_header(request)
    auth_service.logout(db, request.cookies.get(REFRESH_COOKIE))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    return response


@router.get("/me", response_model=MeOut, summary="Current user")
def me(caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    return auth_service.me(db.get(User, caller.user_id))


@router.patch("/me", response_model=MeOut, summary="Change the interface language")
def update_me(data: MeUpdate, caller: Caller = Depends(get_caller), db: Session = Depends(get_db)):
    user = db.get(User, caller.user_id)
    user.locale = data.locale
    db.commit()
    db.refresh(user)
    return auth_service.me(user)
