from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings
from app.security import REFRESH_COOKIE
from tests.conftest import register

CSRF = {"X-Requested-With": "SALVA"}


def test_register_creates_admin_and_session(client):
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Awa@Example.cm",
            "password": "tomates-2026!",
            "organization_name": "Coop  Ouest",
            "locale": "en",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "awa@example.cm"
    assert body["user"]["role"] == "admin" and body["user"]["organization_name"] == "Coop Ouest"
    assert body["expires_in"] == 15 * 60
    cookie = r.headers["set-cookie"]
    assert REFRESH_COOKIE in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/api/v1/auth" in cookie
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["locale"] == "en"


def test_register_validation_and_conflicts(client):
    register(client)
    dup = client.post(
        "/api/v1/auth/register",
        json={
            "email": "awa@example.cm",
            "password": "tomates-2026!",
            "organization_name": "Autre",
        },
    )
    assert dup.status_code == 409 and dup.json()["code"] == "email-taken"
    short = client.post(
        "/api/v1/auth/register",
        json={
            "email": "b@example.cm",
            "password": "court",
            "organization_name": "B org",
        },
    )
    assert short.status_code == 422 and short.json()["errors"][0]["field"] == "password"
    common = client.post(
        "/api/v1/auth/register",
        json={
            "email": "c@example.cm",
            "password": "password123",
            "organization_name": "C org",
        },
    )
    assert common.status_code == 422 and common.json()["errors"][0]["code"] == "weak_password"
    bad_email = client.post(
        "/api/v1/auth/register",
        json={
            "email": "pas-un-email",
            "password": "tomates-2026!",
            "organization_name": "D org",
        },
    )
    assert bad_email.status_code == 422
    extra = client.post(
        "/api/v1/auth/register",
        json={
            "email": "e@example.cm",
            "password": "tomates-2026!",
            "organization_name": "E org",
            "role": "admin",
        },
    )
    assert extra.status_code == 422


def test_login_errors_are_generic_and_lock_after_failures(client):
    register(client)
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@example.cm", "password": "x"})
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "awa@example.cm", "password": "wrong-password"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]
    for _ in range(4):
        client.post(
            "/api/v1/auth/login",
            json={"email": "awa@example.cm", "password": "wrong-password"},
        )
    locked = client.post(
        "/api/v1/auth/login",
        json={"email": "awa@example.cm", "password": "tomates-2026!"},
    )
    assert locked.status_code == 429 and "Retry-After" in locked.headers


def test_refresh_rotates_and_detects_reuse(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "awa@example.cm",
            "password": "tomates-2026!",
            "organization_name": "Coop Ouest",
        },
    )
    first = client.cookies.get(REFRESH_COOKIE)
    assert client.post("/api/v1/auth/refresh").status_code == 403  # custom header required
    r = client.post("/api/v1/auth/refresh", headers=CSRF)
    assert r.status_code == 200 and r.json()["access_token"]
    second = client.cookies.get(REFRESH_COOKIE)
    assert second and second != first
    # Replaying the rotated token revokes the whole family.
    client.cookies.set(REFRESH_COOKIE, first, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh", headers=CSRF).status_code == 401
    client.cookies.set(REFRESH_COOKIE, second, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh", headers=CSRF).status_code == 401


def test_logout_revokes_refresh_token(client):
    register(client)
    assert client.post("/api/v1/auth/logout", headers=CSRF).status_code == 204
    assert client.post("/api/v1/auth/refresh", headers=CSRF).status_code == 401


def test_missing_expired_and_forged_tokens_are_401(client):
    headers = register(client)
    assert client.get("/api/v1/lots").status_code == 401
    token = headers["Authorization"].split()[1]
    claims = jwt.decode(token, options={"verify_signature": False})
    expired = jwt.encode(
        {**claims, "exp": datetime.now(UTC) - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    r = client.get("/api/v1/lots", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.json()["code"] == "token-expired"
    forged = jwt.encode(claims, "another-secret-of-sufficient-length-123456", algorithm="HS256")
    assert client.get("/api/v1/lots", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    none_alg = jwt.encode(claims, key="", algorithm="none")
    assert client.get("/api/v1/lots", headers={"Authorization": f"Bearer {none_alg}"}).status_code == 401


def test_locale_can_be_changed(client, auth):
    r = client.patch("/api/v1/me", headers=auth, json={"locale": "en"})
    assert r.status_code == 200 and r.json()["locale"] == "en"


def test_admin_manages_users_and_operator_rights(client, auth):
    r = client.post(
        "/api/v1/admin/users",
        headers=auth,
        json={
            "email": "paul@example.cm",
            "password": "transport-2026",
            "role": "operator",
        },
    )
    assert r.status_code == 201
    paul_id = r.json()["id"]
    users = client.get("/api/v1/admin/users", headers=auth).json()
    assert {u["email"] for u in users} == {"awa@example.cm", "paul@example.cm"}
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "paul@example.cm", "password": "transport-2026"},
    )
    paul = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/admin/users", headers=paul).status_code == 403
    assert (
        client.patch(f"/api/v1/admin/users/{paul_id}", headers=auth, json={"is_active": False}).status_code
        == 200
    )
    assert client.get("/api/v1/lots", headers=paul).status_code == 401
    me = client.get("/api/v1/me", headers=auth).json()
    selfdemote = client.patch(f"/api/v1/admin/users/{me['id']}", headers=auth, json={"role": "operator"})
    assert selfdemote.status_code == 409
