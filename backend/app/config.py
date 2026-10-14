"""Typed settings read from environment variables (or backend/.env). No secret is hard-coded."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
_DEV_SECRET = "development-only-secret-change-me-0123456789abcdef"  # noqa: S105 - refused in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://salva:salva@localhost:5432/salva"
    reference_dir: Path = REPO_ROOT / "data" / "reference"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    # Comma-separated in the environment: "https://a.example,https://b.example".
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://localhost:8000"]
    max_body_bytes: int = 64 * 1024

    # Authentication (SEC-01, SEC-02)
    jwt_secret: str = _DEV_SECRET
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool | None = None  # None -> secure outside development/test

    # Rate limits (SEC-05)
    rate_auth_per_minute: int = 10
    # Refresh tokens are 256-bit random values, so their limit only bounds page reloads.
    rate_refresh_per_minute: int = 60
    rate_compute_per_hour: int = 60
    rate_explain_per_hour: int = 30

    # Simulation defaults (every value is surfaced to the user as an assumption)
    seed: int = 42
    n_draws: int = 2000
    hold_h: float = 24.0
    transport_fcfa_kg_km: float = 0.10
    road_factor: float = 1.3
    road_speed_kmh: float = 50.0
    sell_local_radius_km: float = 60.0
    max_reroute_options: int = 3
    max_storage_options: int = 2

    # Enrichment
    weather_enabled: bool = True
    weather_base_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_s: float = 4.0
    routing_base_url: str | None = None  # OSRM-compatible service; table + estimate otherwise
    routing_timeout_s: float = 4.0
    default_temp_c: float = 27.0

    # Explanation layer
    llm_provider: Literal["template", "gemini", "openai"] = "template"
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_timeout_s: float = 8.0

    # Demo seed
    demo_user_email: str = "demo@salva.example"
    demo_user_password: str | None = None

    @field_validator("database_url", mode="before")
    @classmethod
    def _psycopg_driver(cls, value):
        """Hosted databases hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the driver."""
        if isinstance(value, str):
            for prefix in ("postgres://", "postgresql://"):
                if value.startswith(prefix):
                    return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str) and not value.strip().startswith("["):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.env == "production":
            if self.jwt_secret == _DEV_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of at least 32 characters")
            if "*" in self.allowed_origins:
                raise ValueError("ALLOWED_ORIGINS cannot contain '*' in production")
        return self

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
