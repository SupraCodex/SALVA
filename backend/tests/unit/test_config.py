"""Settings read from the environment as a hosting platform provides them."""

import pytest

from app.config import Settings


def test_comma_separated_origins_are_accepted(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://salva.onrender.com, http://localhost:8000")
    assert Settings().allowed_origins == ["https://salva.onrender.com", "http://localhost:8000"]


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/salva?sslmode=require",
            "postgresql+psycopg://u:p@ep-x.eu-central-1.aws.neon.tech/salva?sslmode=require",
        ),
        ("postgres://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_database_url_gets_the_psycopg_driver(monkeypatch, given, expected):
    monkeypatch.setenv("DATABASE_URL", given)
    assert Settings().database_url == expected


def test_production_requires_a_real_secret(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(_env_file=None)
