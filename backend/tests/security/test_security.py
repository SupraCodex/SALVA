"""Security checks of design document §37: isolation, roles, injection, limits, headers."""

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import session
from app.main import _mount_frontend
from tests.conftest import add_storage, analyze, create_lot, register, simulate


def test_ca12_other_organization_gets_404_everywhere(client):
    a = register(client, "awa@example.cm", "Coop Ouest")
    b = register(client, "bob@example.cm", "Coop Littoral")
    add_storage(client, a)
    lot = create_lot(client, a)
    an = analyze(client, a, lot["id"])
    sim = simulate(client, a, an["id"])
    reco = sim["recommendation"]["id"]
    checks = [
        ("get", f"/api/v1/lots/{lot['id']}", None),
        ("patch", f"/api/v1/lots/{lot['id']}", {"notes": "x"}),
        ("post", f"/api/v1/lots/{lot['id']}/analyses", {}),
        ("get", f"/api/v1/lots/{lot['id']}/history", None),
        ("post", f"/api/v1/lots/{lot['id']}/outcomes", {"decision_taken": "continue"}),
        ("get", f"/api/v1/analyses/{an['id']}", None),
        ("post", f"/api/v1/analyses/{an['id']}/simulations", {}),
        ("get", f"/api/v1/simulations/{sim['id']}", None),
        ("get", f"/api/v1/simulations/{sim['id']}/recommendation", None),
        ("post", f"/api/v1/simulations/{sim['id']}/sensitivity", {}),
        ("post", f"/api/v1/recommendations/{reco}/explanations", {}),
    ]
    for method, url, body in checks:
        kwargs = {"headers": b} if body is None else {"headers": b, "json": body}
        r = getattr(client, method)(url, **kwargs)
        assert r.status_code == 404, (method, url, r.status_code)
    assert client.get("/api/v1/lots", headers=b).json()["items"] == []
    assert client.get("/api/v1/storage-sites", headers=b).json() == []


def test_operator_cannot_manage_storage_sites(client, auth):
    client.post(
        "/api/v1/admin/users",
        headers=auth,
        json={
            "email": "op@example.cm",
            "password": "operateur-2026",
            "role": "operator",
        },
    )
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "op@example.cm", "password": "operateur-2026"},
    )
    op = {"Authorization": f"Bearer {token.json()['access_token']}"}
    locations = client.get("/api/v1/locations", headers=op).json()
    r = client.post(
        "/api/v1/storage-sites",
        headers=op,
        json={
            "name": "Hangar",
            "location_id": locations[0]["id"],
            "capacity_kg": 100,
            "temp_mode": "ventilated",
        },
    )
    assert r.status_code == 403
    site = add_storage(client, auth)
    assert (
        client.patch(f"/api/v1/storage-sites/{site['id']}", headers=op, json={"capacity_kg": 1}).status_code
        == 403
    )
    assert client.get("/api/v1/storage-sites", headers=op).status_code == 200


def test_sql_and_script_payloads_are_inert(client, auth):
    lot = create_lot(client, auth, notes="<script>alert(1)</script>' OR 1=1 --")
    assert client.get(f"/api/v1/lots/{lot['id']}", headers=auth).json()["notes"].startswith("<script>")
    r = client.get("/api/v1/lots?status=open' OR 1=1 --", headers=auth)
    assert r.status_code == 422
    r = client.post("/api/v1/auth/login", json={"email": "' OR 1=1 --", "password": "' OR 1=1 --"})
    assert r.status_code == 401


def test_rate_limit_returns_429_with_retry_after(client, auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_compute_per_hour", 2)
    lot = create_lot(client, auth)
    codes = [
        client.post(f"/api/v1/lots/{lot['id']}/analyses", headers=auth, json={}).status_code for _ in range(3)
    ]
    assert codes[:2] == [201, 201] and codes[2] == 429


def test_auth_rate_limit_per_ip(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_auth_per_minute", 3)
    codes = [
        client.post("/api/v1/auth/login", json={"email": f"x{i}@example.cm", "password": "x"}).status_code
        for i in range(4)
    ]
    assert codes == [401, 401, 401, 429]


def test_body_size_limit_and_security_headers(client, auth):
    big = client.post(
        "/api/v1/lots",
        headers={**auth, "Content-Type": "application/json"},
        content=b'{"notes": "' + b"a" * 70_000 + b'"}',
    )
    assert big.status_code == 413
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    for header in (
        "X-Content-Type-Options",
        "Referrer-Policy",
        "X-Frame-Options",
        "X-Request-ID",
    ):
        assert header in r.headers
    assert r.headers["Cache-Control"] == "no-store"


def test_cors_only_allows_configured_origins(client):
    allowed = get_settings().allowed_origins[0]
    ok = client.options(
        "/api/v1/lots",
        headers={"Origin": allowed, "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == allowed
    evil = client.options(
        "/api/v1/lots",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in evil.headers


def test_health_reports_model_and_no_secret(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["model"]["name"] == "kinetic"
    assert "jwt" not in str(body).lower() and "key" not in str(body).lower()


def test_production_settings_refuse_default_secret(monkeypatch):
    import pytest

    from app.config import _DEV_SECRET, Settings

    with pytest.raises(ValueError):
        Settings(env="production", jwt_secret=_DEV_SECRET)
    with pytest.raises(ValueError):
        Settings(env="production", jwt_secret="too-short")
    with pytest.raises(ValueError):
        Settings(env="production", jwt_secret="x" * 40, allowed_origins=["*"])
    assert Settings(env="production", jwt_secret="x" * 40).secure_cookies


def test_session_refresh_has_its_own_budget(client, monkeypatch):
    """Page reloads refresh the session; they must not lock the user out of signing in."""
    monkeypatch.setattr(get_settings(), "rate_auth_per_minute", 2)
    monkeypatch.setattr(get_settings(), "rate_refresh_per_minute", 3)
    csrf = {"X-Requested-With": "SALVA"}
    refreshes = [client.post("/api/v1/auth/refresh", headers=csrf).status_code for _ in range(4)]
    assert refreshes == [401, 401, 401, 429]
    login = client.post("/api/v1/auth/login", json={"email": "y@example.cm", "password": "x"})
    assert login.status_code == 401


def test_frontend_assets_are_compressed_and_cached(tmp_path, monkeypatch):

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>SALVA</title>")
    (tmp_path / "assets" / "app-abc.js").write_text("console.log('salva');" * 200)
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    _mount_frontend(app, tmp_path)
    c = TestClient(app)
    js = c.get("/assets/app-abc.js", headers={"Accept-Encoding": "gzip"})
    assert js.headers["content-encoding"] == "gzip"
    assert "immutable" in js.headers["cache-control"]
    page = c.head("/lots/x/analysis")
    assert page.status_code == 200
    assert c.get("/lots/x/analysis").headers["cache-control"] == "no-cache"


def test_liveness_does_not_need_the_database(client, monkeypatch):
    def broken():
        raise AssertionError("the liveness probe must not open a database session")

    monkeypatch.setattr(session, "get_sessionmaker", broken)
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
