"""Start-up check: explicit failures, no secret in the output."""

from __future__ import annotations

import pytest

from app import preflight


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("ENV", "JWT_SECRET", "DATABASE_URL", "ALLOWED_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(preflight, "WAIT_S", 0)
    monkeypatch.setattr(preflight, "ATTEMPTS", 1)


def test_production_without_secret_fails(monkeypatch, capsys):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:topsecretpw@db.example:5432/x")
    assert preflight.main() == 1
    err = capsys.readouterr().err
    assert "PREFLIGHT ERROR" in err and "JWT_SECRET" in err
    assert "topsecretpw" not in err


def test_production_with_local_database_fails(monkeypatch, capsys):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://salva.example")
    monkeypatch.setenv("DATABASE_URL", "postgresql://salva:salva@localhost:5432/salva")
    assert preflight.main() == 1
    assert "DATABASE_URL is not set" in capsys.readouterr().err


def test_unreachable_database_fails_without_password(monkeypatch, capsys):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://salva.example")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:topsecretpw@nowhere.invalid:5432/x")
    assert preflight.main() == 1
    out = capsys.readouterr()
    assert "cannot connect to the database at nowhere.invalid" in out.err
    assert "topsecretpw" not in out.err + out.out
