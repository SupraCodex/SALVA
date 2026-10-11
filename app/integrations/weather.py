"""Open-Meteo client (no API key) with a hard timeout and a 3 h in-memory cache.
Returns None on any failure: the caller falls back to manual input, then to a labelled default."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

import httpx

from app.config import get_settings

log = logging.getLogger("salva.weather")
URL = "https://api.open-meteo.com/v1/forecast"
_CACHE: dict[tuple, tuple[float, float]] = {}
_TTL_S = 3 * 3600


def mean_temperature(lat: float, lon: float, start: datetime, end: datetime) -> float | None:
    s = get_settings()
    if not s.weather_enabled:
        return None
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    key = (round(lat, 2), round(lon, 2), start.strftime("%Y%m%d%H"), end.strftime("%Y%m%d%H"))
    hit = _CACHE.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    now = datetime.now(UTC)
    try:
        r = httpx.get(URL, timeout=s.weather_timeout_s, params={
            "latitude": lat, "longitude": lon, "hourly": "temperature_2m", "timezone": "UTC",
            "past_days": min(92, max(0, (now - start).days + 1)),
            "forecast_days": min(16, max(1, (end - now).days + 2))})
        r.raise_for_status()
        h = r.json()["hourly"]
        vals = [float(v) for t, v in zip(h["time"], h["temperature_2m"], strict=False)
                if v is not None and start - timedelta(hours=1)
                <= datetime.fromisoformat(t).replace(tzinfo=UTC) <= end + timedelta(hours=1)]
        if not vals:
            return None
        mean = round(sum(vals) / len(vals), 1)
        _CACHE[key] = (time.monotonic() + _TTL_S, mean)
        return mean
    except Exception as e:  # network, quota, format
        log.warning("weather_unavailable: %s", type(e).__name__)
        return None
