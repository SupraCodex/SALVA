"""Automatic enrichment with provenance (FR-03, DAT-01): temperature, route and reference price.

Temperature: manual value, else Open-Meteo over the harvest -> arrival window at the origin
and destination, else the configured default labelled as an assumption. Air temperature is
not product temperature: the packaging offset is applied later by the core.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config import get_settings
from app.db.models import Location, Lot, Market
from app.integrations import routing, weather


@dataclass(frozen=True)
class Value:
    value: float
    source: str


@dataclass(frozen=True)
class Temperature:
    mean: Value
    half_amplitude: Value
    automatic: bool


def temperature_for(
    origin: Location,
    destination: Market,
    start: datetime,
    end: datetime,
    manual: float | None,
) -> Temperature:
    settings = get_settings()
    summary = weather.summarize(
        [
            (origin.lat, origin.lon),
            (destination.location.lat, destination.location.lon),
        ],
        start,
        end,
    )
    if manual is not None:
        amp = (
            Value(summary.half_amplitude_c, "open-meteo")
            if summary
            else Value(_default_amp(), "assumption: product default")
        )
        return Temperature(Value(float(manual), "manual"), amp, summary is not None)
    if summary is not None:
        return Temperature(
            Value(summary.mean_c, "open-meteo"),
            Value(summary.half_amplitude_c, "open-meteo"),
            True,
        )
    return Temperature(
        Value(
            settings.default_temp_c,
            "assumption: default temperature (weather service unavailable)",
        ),
        Value(_default_amp(), "assumption: product default"),
        False,
    )


def _default_amp() -> float:
    from app.services import engine

    return float(engine.params("tomato").default_diurnal_amp_c)


def temperature(lot: Lot, now: datetime) -> Temperature:
    end = max(lot.eta_current_at, now)
    return temperature_for(lot.origin, lot.destination, lot.harvested_at, end, lot.temp_override_c)


def price(lot: Lot) -> Value:
    if lot.price_override_fcfa_kg is not None:
        return Value(float(lot.price_override_fcfa_kg), "manual")
    return Value(
        float(lot.destination.ref_price_fcfa_kg),
        f"reference: {lot.destination.assumption_note}",
    )


def route(origin: Location, destination: Market) -> routing.Leg:
    loc = destination.location
    return routing.leg(origin.code, origin.lat, origin.lon, loc.code, loc.lat, loc.lon)
