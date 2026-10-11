"""Typed settings read from .env. No secret is hard-coded."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://salva:salva@localhost:5432/salva"
    reference_dir: Path = REPO_ROOT / "data" / "reference"
    allowed_origins: list[str] = ["http://localhost:3000"]

    # Simulation
    seed: int = 42
    n_draws: int = 2000
    hold_h: float = 24.0                 # storage duration simulated for the "store" action
    transport_fcfa_kg_km: float = 0.06   # extra transport cost
    sell_local_radius_km: float = 60.0
    max_reroute_options: int = 3

    # Weather (Open-Meteo, no key). Fallback: manual value, then default labelled "assumption"
    weather_enabled: bool = True
    weather_timeout_s: float = 3.0
    default_temp_c: float = 27.0

    # Explanation layer (owned by R5, module app.llm.service). The API only enforces a time limit.
    llm_timeout_s: float = 10.0

    # Wave 2: authentication. Disabled -> every request uses the seeded "demo" organization
    auth_enabled: bool = False
    jwt_secret: str = "dev-only-change-me-with-a-long-random-string"
    access_token_minutes: int = 60
    cookie_secure: bool = False
    rate_limit_per_min: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
