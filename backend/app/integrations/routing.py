"""Road distance and duration between two places, with a documented fallback chain.

1. ``data/reference/distances.csv`` (team estimates, each row carries its source);
2. an OSRM-compatible routing service when ``ROUTING_BASE_URL`` is configured;
3. a great-circle estimate x road factor at an average speed, labelled as an assumption.

The result always says which of the three produced it (DAT-01).
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import get_settings

log = logging.getLogger("salva.routing")
_OSRM_CACHE: dict[tuple, Leg | None] = {}


@dataclass(frozen=True)
class Leg:
    km: float
    hours: float
    source: str


@lru_cache
def _table() -> dict[tuple[str, str], Leg]:
    path = get_settings().reference_dir / "distances.csv"
    out: dict[tuple[str, str], Leg] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            leg = Leg(
                float(row["distance_km"]),
                float(row["duree_h"]),
                f"distances.csv: {row['source']}",
            )
            a, b = row["origine_id"].strip(), row["destination_id"].strip()
            out[(a, b)] = leg
            out.setdefault((b, a), leg)
    return out


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _osrm(lat1: float, lon1: float, lat2: float, lon2: float) -> Leg | None:
    settings = get_settings()
    if not settings.routing_base_url:
        return None
    key = (round(lat1, 4), round(lon1, 4), round(lat2, 4), round(lon2, 4))
    if key in _OSRM_CACHE:
        return _OSRM_CACHE[key]
    url = f"{settings.routing_base_url.rstrip('/')}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    try:
        resp = httpx.get(url, params={"overview": "false"}, timeout=settings.routing_timeout_s)
        resp.raise_for_status()
        route = resp.json()["routes"][0]
        leg = Leg(
            round(route["distance"] / 1000, 1),
            round(route["duration"] / 3600, 2),
            "osrm routing service",
        )
    except Exception as exc:  # noqa: BLE001 - routing is optional, fall back to the estimate
        log.warning("routing_unavailable", extra={"reason": type(exc).__name__})
        leg = None
    _OSRM_CACHE[key] = leg
    return leg


def leg(code_a: str, lat_a: float, lon_a: float, code_b: str, lat_b: float, lon_b: float) -> Leg:
    """Distance and duration from place A to place B (codes are reference ids such as L01/M02)."""
    if code_a == code_b:
        return Leg(0.0, 0.0, "same place")
    hit = _table().get((code_a, code_b))
    if hit is not None:
        return hit
    routed = _osrm(lat_a, lon_a, lat_b, lon_b)
    if routed is not None:
        return routed
    settings = get_settings()
    km = haversine_km(lat_a, lon_a, lat_b, lon_b) * settings.road_factor
    if km < 0.5:
        return Leg(0.0, 0.0, "same place")
    return Leg(
        round(km, 1),
        round(km / settings.road_speed_kmh, 2),
        f"assumption: great-circle distance x {settings.road_factor} at {settings.road_speed_kmh:g} km/h",
    )
