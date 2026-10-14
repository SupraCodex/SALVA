"""Open-Meteo client (no API key): hourly 2 m air temperature, hard timeout, 3 h cache.

Returns ``None`` on any failure so the caller can fall back to a manual value, then to a
default clearly labelled as an assumption (NFR-04). The forecast endpoint serves both past
days (up to 92) and forecast days (up to 16), which also covers replayed analyses.
Docs: https://open-meteo.com/en/docs
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.config import get_settings

log = logging.getLogger("salva.weather")
_CACHE: dict[tuple, tuple[float, WeatherSummary | None]] = {}
_TTL_S = 3 * 3600


@dataclass(frozen=True)
class WeatherSummary:
    mean_c: float
    half_amplitude_c: float
    hours: int


def _summarize(times: list[str], temps: list[float | None], start: datetime, end: datetime):
    picked: list[tuple[datetime, float]] = []
    for t, v in zip(times, temps, strict=False):
        if v is None:
            continue
        at = datetime.fromisoformat(t).replace(tzinfo=UTC)
        if start - timedelta(hours=1) <= at <= end + timedelta(hours=1):
            picked.append((at, float(v)))
    if not picked:
        return None
    values = [v for _, v in picked]
    by_day: dict[str, list[float]] = {}
    for at, v in picked:
        by_day.setdefault(at.strftime("%Y-%m-%d"), []).append(v)
    full_days = [d for d in by_day.values() if len(d) >= 12]
    if full_days:
        amp = sum((max(d) - min(d)) / 2 for d in full_days) / len(full_days)
    else:
        amp = (max(values) - min(values)) / 2
    return WeatherSummary(round(sum(values) / len(values), 1), round(amp, 1), len(values))


def summarize(points: list[tuple[float, float]], start: datetime, end: datetime) -> WeatherSummary | None:
    """Mean temperature and mean daily half-amplitude over [start, end] across several points."""
    settings = get_settings()
    if not settings.weather_enabled:
        return None
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if end < start:
        start, end = end, start
    key = (
        tuple((round(lat, 2), round(lon, 2)) for lat, lon in points),
        start.strftime("%Y%m%d%H"),
        end.strftime("%Y%m%d%H"),
    )
    hit = _CACHE.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    now = datetime.now(UTC)
    past_days = min(92, max(0, (now - start).days + 1))
    forecast_days = min(16, max(1, (end - now).days + 2))
    summaries: list[WeatherSummary] = []
    try:
        with httpx.Client(timeout=settings.weather_timeout_s) as client:
            for lat, lon in points:
                resp = client.get(
                    settings.weather_base_url,
                    params={
                        "latitude": round(lat, 4),
                        "longitude": round(lon, 4),
                        "hourly": "temperature_2m",
                        "timezone": "UTC",
                        "past_days": past_days,
                        "forecast_days": forecast_days,
                    },
                )
                resp.raise_for_status()
                hourly = resp.json()["hourly"]
                summary = _summarize(hourly["time"], hourly["temperature_2m"], start, end)
                if summary is not None:
                    summaries.append(summary)
    except Exception as exc:  # noqa: BLE001 - network, quota, format: degrade gracefully
        log.warning("weather_unavailable", extra={"reason": type(exc).__name__})
        return None
    if not summaries:
        result = None
    else:
        hours = sum(s.hours for s in summaries)
        result = WeatherSummary(
            round(sum(s.mean_c * s.hours for s in summaries) / hours, 1),
            round(sum(s.half_amplitude_c * s.hours for s in summaries) / hours, 1),
            hours,
        )
    _CACHE[key] = (time.monotonic() + _TTL_S, result)
    return result


def clear_cache() -> None:
    _CACHE.clear()
