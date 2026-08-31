"""Open-Meteo weather normalization and deterministic trip guidance."""

import json
import os
import time
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .models import WEATHER_API_URL
from .telemetry import emit_event
from .tracing import trace_span

_WEATHER_CACHE: OrderedDict[tuple[float, float], tuple[float, list[dict[str, object]]]] = OrderedDict()
_DEFAULT_WEATHER_CACHE_TTL_SECONDS = 300
_DEFAULT_WEATHER_CACHE_MAX_ENTRIES = 64


def _weather_cache_ttl_seconds() -> float:
    try:
        configured = float(os.getenv("WEATHER_CACHE_TTL_SECONDS", str(_DEFAULT_WEATHER_CACHE_TTL_SECONDS)))
    except ValueError:
        configured = _DEFAULT_WEATHER_CACHE_TTL_SECONDS
    return max(0.0, min(configured, 3600.0))


def _weather_cache_max_entries() -> int:
    try:
        configured = int(os.getenv("WEATHER_CACHE_MAX_ENTRIES", str(_DEFAULT_WEATHER_CACHE_MAX_ENTRIES)))
    except ValueError:
        configured = _DEFAULT_WEATHER_CACHE_MAX_ENTRIES
    return max(1, min(configured, 256))


def clear_weather_cache() -> None:
    """Clear the process-local cache; used by tests and controlled experiments."""
    _WEATHER_CACHE.clear()


def _weather_cache_key(latitude: float, longitude: float) -> tuple[float, float]:
    return (round(latitude, 6), round(longitude, 6))


def fetch_weather(latitude: float, longitude: float) -> list[dict[str, object]]:
    cache_key = _weather_cache_key(latitude, longitude)
    cached = _WEATHER_CACHE.get(cache_key)
    if cached is not None:
        cached_at, forecast = cached
        if time.monotonic() - cached_at <= _weather_cache_ttl_seconds():
            _WEATHER_CACHE.move_to_end(cache_key)
            emit_event("weather_cache", "hit", provider="open_meteo", metrics={"WeatherCacheHits": 1})
            return forecast
        _WEATHER_CACHE.pop(cache_key, None)
    emit_event("weather_cache", "miss", provider="open_meteo", metrics={"WeatherCacheMisses": 1})
    started = time.perf_counter()
    query = urlencode({"latitude": f"{latitude:.6f}", "longitude": f"{longitude:.6f}", "hourly": "temperature_2m,precipitation_probability,precipitation,rain,wind_speed_10m,wind_gusts_10m,weather_code", "forecast_days": "2", "timezone": "auto"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with trace_span("weather.lookup", provider="open_meteo"), urlopen(f"{WEATHER_API_URL}?{query}", timeout=3) as response:
                payload = json.loads(response.read(65536).decode("utf-8"))
            break
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            last_error = error
            if isinstance(error, HTTPError) and error.code < 500:
                raise
            if attempt == 2:
                raise
            time.sleep(0.05 * (2**attempt))
    else:
        raise last_error or RuntimeError("weather_provider_unavailable")
    duration_ms = (time.perf_counter() - started) * 1000
    emit_event("weather_call", "success", provider="open_meteo", duration_ms=duration_ms, metrics={"WeatherCalls": 1, "WeatherCallDurationMs": duration_ms})
    forecast = normalize_hourly_weather(payload)
    _WEATHER_CACHE[cache_key] = (time.monotonic(), forecast)
    _WEATHER_CACHE.move_to_end(cache_key)
    while len(_WEATHER_CACHE) > _weather_cache_max_entries():
        _WEATHER_CACHE.popitem(last=False)
    return forecast


def normalize_hourly_weather(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("hourly"), Mapping):
        raise TypeError("missing_hourly_weather")
    hourly = payload["hourly"]
    keys = ("time", "temperature_2m", "precipitation_probability", "precipitation", "rain", "wind_speed_10m", "wind_gusts_10m", "weather_code")
    columns = {key: hourly.get(key) for key in keys}
    if not all(isinstance(value, list) and value for value in columns.values()):
        raise ValueError("missing_hourly_fields")
    length = len(columns["time"])
    if any(len(value) != length for value in columns.values()):
        raise ValueError("misaligned_hourly_fields")
    periods: list[dict[str, object]] = []
    for index in range(length):
        timestamp = columns["time"][index]
        if not isinstance(timestamp, str):
            raise TypeError("invalid_hourly_time")
        periods.append({"time": timestamp, "temperature_c": number(columns["temperature_2m"][index]), "precipitation_probability": number(columns["precipitation_probability"][index]), "precipitation_mm": number(columns["precipitation"][index]), "rain_mm": number(columns["rain"][index]), "wind_kmh": number(columns["wind_speed_10m"][index]), "gust_kmh": number(columns["wind_gusts_10m"][index]), "weather_code": number(columns["weather_code"][index])})
    return periods


def select_weather_period(periods: list[dict[str, object]], time_window: str) -> dict[str, object]:
    normalized = time_window.lower()
    first_day = str(periods[0]["time"])[:10]
    candidates = [p for p in periods if str(p["time"])[:10] > first_day] if "tomorrow" in normalized else periods
    candidates = candidates or periods
    desired_hour = 9 if "morning" in normalized else 18 if "tonight" in normalized else None
    if desired_hour is not None:
        for period in candidates:
            if str(period["time"])[11:13] == f"{desired_hour:02d}":
                return period
    return candidates[0]


def trip_guidance(weather: Mapping[str, object], activity: str) -> list[str]:
    guidance: list[str] = []
    gust, wind = float(cast(Any, weather["gust_kmh"])), float(cast(Any, weather["wind_kmh"]))
    rain_probability, precipitation = float(cast(Any, weather["precipitation_probability"])), float(cast(Any, weather["precipitation_mm"]))
    temperature = float(cast(Any, weather["temperature_c"]))
    if gust >= 40:
        guidance.append("Avoid open-water canoeing; gusts are high.")
    elif gust >= 30 or wind >= 25:
        guidance.append("Canoe early or stay near shore; wind may build.")
    if rain_probability >= 60 or precipitation >= 1:
        guidance.append("Set the tarp before rain.")
    if temperature <= 5:
        guidance.append("Plan warm, dry layers for cold conditions.")
    if not guidance:
        guidance.append("No major weather trigger in this forecast hour; keep normal caution.")
    if "cano" in activity.lower() and gust >= 30:
        guidance.append("Avoid exposed crossings if conditions worsen.")
    return guidance


def deterministic_weather_summary(weather: Mapping[str, object], guidance: list[str]) -> str:
    return f"{weather['temperature_c']:.0f}C, rain {weather['precipitation_probability']:.0f}%, gusts {weather['gust_kmh']:.0f} km/h. {guidance[0]}"


def number(value: object) -> float:
    if not isinstance(value, (int, float)):
        raise TypeError("invalid_weather_number")
    return float(value)
