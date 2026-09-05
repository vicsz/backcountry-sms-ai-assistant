"""Unit coverage for the bounded, expiring weather cache."""

from typing import Self

import pytest

from backcountry_sms import weather

pytestmark = pytest.mark.legacy_python_runtime


def _payload() -> dict[str, object]:
    values = list(range(2))
    return {
        "hourly": {
            "time": ["2026-08-30T12:00", "2026-08-30T13:00"],
            "temperature_2m": values,
            "precipitation_probability": values,
            "precipitation": values,
            "rain": values,
            "wind_speed_10m": values,
            "wind_gusts_10m": values,
            "weather_code": values,
        }
    }


def test_successful_weather_is_cached(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(weather, "urlopen", lambda *_args, **_kwargs: _Response(_payload(), calls))
    weather.clear_weather_cache()

    first = weather.fetch_weather(45.6200001, -78.4200001)
    second = weather.fetch_weather(45.62, -78.42)

    assert first == second
    assert len(calls) == 1


def test_bug_0002_open_water_guidance_prioritizes_crossing_factors() -> None:
    guidance = weather.trip_guidance(
        {"temperature_c": 20, "precipitation_probability": 45, "precipitation_mm": 1.2, "wind_kmh": 12, "gust_kmh": 20},
        "open-water crossing",
    )

    assert guidance[0] == "Watch wind, rain, and visibility; stay near shore if conditions worsen."
    assert "tarp" not in guidance[0].lower()


def test_expired_weather_is_refetched(monkeypatch) -> None:
    calls = []
    now = iter([100.0, 101.0, 200.0, 201.0])
    monkeypatch.setattr(weather, "time", type("Clock", (), {"monotonic": staticmethod(lambda: next(now)), "perf_counter": staticmethod(lambda: 0.0), "sleep": staticmethod(lambda _seconds: None)})())
    monkeypatch.setenv("WEATHER_CACHE_TTL_SECONDS", "60")
    monkeypatch.setattr(weather, "urlopen", lambda *_args, **_kwargs: _Response(_payload(), calls))
    weather.clear_weather_cache()

    weather.fetch_weather(45.62, -78.42)
    weather.fetch_weather(45.62, -78.42)
    weather.fetch_weather(45.62, -78.42)

    assert len(calls) == 2


def test_noon_weather_window_selects_midday_period() -> None:
    periods = [
        {"time": "2026-09-01T09:00", "temperature_c": 15},
        {"time": "2026-09-01T12:00", "temperature_c": 20},
        {"time": "2026-09-01T15:00", "temperature_c": 22},
    ]

    assert weather.select_weather_period(periods, "noon")["time"] == "2026-09-01T12:00"
    assert weather.select_weather_period(periods, "midday")["time"] == "2026-09-01T12:00"


class _Response:
    def __init__(self, payload: dict[str, object], calls: list[bool]) -> None:
        self.payload = payload
        self.calls = calls

    def __enter__(self) -> Self:
        self.calls.append(True)
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        import json

        return json.dumps(self.payload).encode()
