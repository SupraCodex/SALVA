"""Test configuration.

By default the suite runs on a temporary SQLite database. Set TEST_DATABASE_URL to run the
same tests on PostgreSQL (the CI does). The schema is created with the Alembic migrations,
so every run also verifies them.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="salva-tests-"))
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_TMP / 'test.db'}")
os.environ.setdefault("ENV", "test")
os.environ["WEATHER_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "template"
os.environ["RATE_AUTH_PER_MINUTE"] = "1000"
os.environ["RATE_COMPUTE_PER_HOUR"] = "10000"
os.environ["RATE_EXPLAIN_PER_HOUR"] = "10000"
os.environ["N_DRAWS"] = "1000"
os.environ["FRONTEND_DIST"] = str(_TMP / "no-frontend")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-0123456789")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import rate_limit
from app.db.models import Base
from app.db.session import get_engine, get_sessionmaker
from app.main import app
from app.seed import seed_reference

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _schema():
    engine = get_engine()
    with engine.begin() as conn:
        Base.metadata.drop_all(conn)
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean_db(_schema):
    engine = get_engine()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    db = get_sessionmaker()()
    try:
        seed_reference(db)
    finally:
        db.close()
    rate_limit.reset()
    yield


@pytest.fixture
def db():
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(
    client: TestClient,
    email: str = "awa@example.cm",
    org: str = "Coop Ouest",
    password: str = "tomates-2026!",
    locale: str = "fr",
) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "organization_name": org,
            "locale": locale,
        },
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


def reference(client: TestClient, headers: dict[str, str]) -> tuple[dict, dict]:
    locations = {loc["code"]: loc for loc in client.get("/api/v1/locations", headers=headers).json()}
    markets = {m["code"]: m for m in client.get("/api/v1/markets", headers=headers).json()}
    return locations, markets


def demo_lot_payload(client: TestClient, headers: dict[str, str], **overrides) -> dict:
    locations, markets = reference(client, headers)
    payload = {
        "product_code": "tomato",
        "quantity_kg": 500,
        "harvested_at": "2026-10-01T06:00:00Z",
        "maturity": "breaker",
        "packaging": "crate",
        "origin_location_id": locations["L01"]["id"],
        "destination_market_id": markets["M01"]["id"],
        "eta_planned_at": "2026-10-03T14:00:00Z",
        "eta_current_at": "2026-10-04T02:00:00Z",
        "notes": "lot de la coopérative nord",
    }
    payload.update(overrides)
    return payload


def add_storage(client: TestClient, headers: dict[str, str], capacity: float = 200.0) -> dict:
    locations, _ = reference(client, headers)
    r = client.post(
        "/api/v1/storage-sites",
        headers=headers,
        json={
            "name": "Relais de Bafang",
            "location_id": locations["L02"]["id"],
            "capacity_kg": capacity,
            "temp_mode": "ambient_shade",
            "cost_fcfa_kg_day": 5,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def create_lot(client: TestClient, headers: dict[str, str], **overrides) -> dict:
    r = client.post(
        "/api/v1/lots",
        headers=headers,
        json=demo_lot_payload(client, headers, **overrides),
    )
    assert r.status_code == 201, r.text
    return r.json()


def analyze(
    client: TestClient,
    headers: dict[str, str],
    lot_id: str,
    at: str = "2026-10-03T08:00:00Z",
) -> dict:
    r = client.post(f"/api/v1/lots/{lot_id}/analyses", headers=headers, json={"analysis_at": at})
    assert r.status_code == 201, r.text
    return r.json()


def simulate(client: TestClient, headers: dict[str, str], analysis_id: str, **body) -> dict:
    r = client.post(f"/api/v1/analyses/{analysis_id}/simulations", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()
