"""Temperature: manual value, else Open-Meteo (3 s max), else a default labelled 'assumption'."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config import get_settings
from app.db.models import Lot
from app.integrations import weather


@dataclass(frozen=True)
class Sourced:
    value: float
    source: str  # manual | open-meteo | assumption


def temperature(lot: Lot, now: datetime) -> Sourced:
    if lot.temp_override_c is not None:
        return Sourced(lot.temp_override_c, "manual")
    t = weather.mean_temperature(lot.origin.lat, lot.origin.lon, lot.harvested_at, max(lot.eta_current, now))
    if t is not None:
        return Sourced(t, "open-meteo")
    return Sourced(get_settings().default_temp_c, "assumption")


def price(lot: Lot) -> Sourced:
    if lot.price_override_fcfa_kg is not None:
        return Sourced(lot.price_override_fcfa_kg, "manual")
    return Sourced(lot.destination.ref_price_fcfa_kg, f"markets.csv ({lot.destination.source})")
