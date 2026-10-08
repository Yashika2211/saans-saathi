"""Hourly PM2.5 / PM10 from the Open-Meteo Air Quality API (CAMS forecast).

Live forecasts and replays of past days both come from the same endpoint.
Every response is cached as JSON so demos and tests never depend on the network.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEZONE = "Asia/Kolkata"

# Bundled fixtures (read-only in Lambda) and a writable cache (defaults to the same place locally).
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
CACHE_DIR = Path(os.environ.get("SAANS_CACHE_DIR", FIXTURES_DIR))


class ForecastError(RuntimeError):
    pass


@dataclass(frozen=True)
class HourReading:
    time: datetime  # local time, Asia/Kolkata, naive
    pm25: float | None
    pm10: float | None


def _cache_name(lat: float, lon: float, start: date, end: date) -> str:
    return f"openmeteo_{lat:.4f}_{lon:.4f}_{start.isoformat()}_{end.isoformat()}.json"


def _build_url(lat: float, lon: float, start: date | None, end: date | None, days: int) -> str:
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "hourly": "pm2_5,pm10",
        "timezone": TIMEZONE,
    }
    if start and end:
        params["start_date"] = start.isoformat()
        params["end_date"] = end.isoformat()
    else:
        params["forecast_days"] = str(days)
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def _read_cached(name: str) -> dict | None:
    for folder in (CACHE_DIR, FIXTURES_DIR):
        path = folder / name
        if path.exists():
            return json.loads(path.read_text())
    return None


def _write_cache(name: str, payload: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / name).write_text(json.dumps(payload, indent=1))
    except OSError:
        pass  # read-only filesystem (e.g. Lambda package dir); caching is best effort


def _download(url: str, timeout: float = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "SaansSaathi/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # network, HTTP or JSON errors all mean "no fresh data"
        raise ForecastError(f"Open-Meteo request failed: {exc}") from exc


def parse(payload: dict) -> list[HourReading]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    pm25 = hourly.get("pm2_5") or [None] * len(times)
    pm10 = hourly.get("pm10") or [None] * len(times)
    if not times:
        raise ForecastError("Open-Meteo response has no hourly data")
    return [
        HourReading(time=datetime.fromisoformat(t), pm25=a, pm10=b)
        for t, a, b in zip(times, pm25, pm10)
    ]


def get_hourly(
    lat: float,
    lon: float,
    day: date,
    *,
    replay: bool = False,
    offline: bool = False,
) -> list[HourReading]:
    """Hourly readings for one local calendar day.

    replay=True fetches a past day with start_date/end_date and prefers the cache, so a
    replayed demo is always identical. Live mode fetches a 3-day forecast and falls back
    to the cache if the network fails.
    """
    if replay:
        name = _cache_name(lat, lon, day, day)
        payload = _read_cached(name)
        if payload is None:
            if offline:
                raise ForecastError(f"No cached replay for {day} at {lat},{lon}")
            payload = _download(_build_url(lat, lon, day, day, 1))
            _write_cache(name, payload)
    else:
        name = f"openmeteo_{lat:.4f}_{lon:.4f}_live_{day.isoformat()}.json"
        payload = None
        if not offline:
            try:
                payload = _download(_build_url(lat, lon, None, None, 3))
                _write_cache(name, payload)
            except ForecastError:
                payload = None
        if payload is None:
            payload = _read_cached(name)
        if payload is None:
            raise ForecastError(f"No forecast available for {day} at {lat},{lon}")

    readings = [r for r in parse(payload) if r.time.date() == day]
    if not readings:
        raise ForecastError(f"Forecast has no hours for {day}")
    return readings
