from datetime import UTC, datetime

import httpx
import pytest

from app.config import get_settings
from app.integrations import routing, weather


def test_distance_table_is_symmetric_and_sourced():
    leg = routing.leg("L01", 5.443, 10.053, "M02", 5.476, 10.418)
    assert leg.km == 30 and leg.hours == 0.75 and leg.source.startswith("distances.csv")
    back = routing.leg("M02", 5.476, 10.418, "L01", 5.443, 10.053)
    assert (back.km, back.hours) == (leg.km, leg.hours)


def test_unknown_pair_uses_labelled_great_circle_estimate():
    leg = routing.leg("L01", 5.443, 10.053, "M03", 3.865, 11.515)
    expected = routing.haversine_km(5.443, 10.053, 3.865, 11.515) * get_settings().road_factor
    assert leg.km == pytest.approx(expected, abs=0.1)
    assert leg.source.startswith("assumption")


def test_same_coordinates_are_the_same_place():
    assert routing.leg("L01", 5.443, 10.053, "M04", 5.443, 10.053).km == 0.0


def _fake_client(handler):
    real = httpx.Client

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    return factory


def test_weather_summary_mean_and_amplitude(monkeypatch):
    monkeypatch.setattr(get_settings(), "weather_enabled", True)
    weather.clear_cache()
    times = [f"2026-10-01T{h:02d}:00" for h in range(24)]
    temps = [22 + 8 * (1 if 10 <= h <= 16 else 0) for h in range(24)]

    def handler(request):
        assert request.url.params["hourly"] == "temperature_2m"
        return httpx.Response(200, json={"hourly": {"time": times, "temperature_2m": temps}})

    monkeypatch.setattr(weather.httpx, "Client", _fake_client(handler))
    start = datetime(2026, 10, 1, 0, tzinfo=UTC)
    end = datetime(2026, 10, 1, 23, tzinfo=UTC)
    summary = weather.summarize([(5.4, 10.0)], start, end)
    assert summary is not None
    assert summary.mean_c == pytest.approx(sum(temps) / 24, abs=0.1)
    assert summary.half_amplitude_c == pytest.approx(4.0)
    weather.clear_cache()


def test_weather_failure_returns_none(monkeypatch):
    monkeypatch.setattr(get_settings(), "weather_enabled", True)
    weather.clear_cache()
    monkeypatch.setattr(weather.httpx, "Client", _fake_client(lambda request: httpx.Response(503)))
    now = datetime.now(UTC)
    assert weather.summarize([(5.4, 10.0)], now, now) is None
    weather.clear_cache()


def test_osrm_is_used_when_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "routing_base_url", "https://router.example")
    routing._OSRM_CACHE.clear()

    def fake_get(url, params=None, timeout=None):
        assert "/route/v1/driving/" in url
        return httpx.Response(
            200,
            json={"routes": [{"distance": 123400.0, "duration": 9000.0}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(routing.httpx, "get", fake_get)
    leg = routing.leg("X1", 5.0, 10.0, "X2", 4.0, 9.0)
    assert (leg.km, leg.hours, leg.source) == (123.4, 2.5, "osrm routing service")
    routing._OSRM_CACHE.clear()
