"""NOAA weather context (a.md §8.4).

Used to add an "AC load / heat" narrative on top of the EIA carbon
intensity. Uses NOAA's free public weather forecast API
(`api.weather.gov`), which doesn't require a token. We pick one
representative point per balancing authority — exact precision isn't the
goal, the *story* (current temperature + 24h max) is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Tuple

import httpx

logger = logging.getLogger(__name__)


# Lat/lon points roughly inside each BA's main demand center.
REGION_POINTS: dict[str, Tuple[float, float, str]] = {
    "CISO": (34.05, -118.25, "Los Angeles, CA"),
    "ERCO": (29.76, -95.37, "Houston, TX"),
    "PJM": (40.44, -79.99, "Pittsburgh, PA"),
    "MISO": (41.88, -87.63, "Chicago, IL"),
    "NYIS": (40.71, -74.01, "New York, NY"),
}


@dataclass
class WeatherSnapshot:
    region: str
    location_label: str
    temperature_f: float | None
    high_24h_f: float | None
    short_forecast: str | None
    fetched_at: datetime


def fetch_weather(region: str) -> WeatherSnapshot | None:
    if region not in REGION_POINTS:
        return None
    lat, lon, label = REGION_POINTS[region]
    headers = {"User-Agent": "GridGreen/0.1 (hackathon demo)"}

    try:
        with httpx.Client(timeout=15.0, headers=headers) as client:
            meta = client.get(f"https://api.weather.gov/points/{lat},{lon}")
            meta.raise_for_status()
            forecast_url = meta.json()["properties"]["forecastHourly"]

            forecast = client.get(forecast_url)
            forecast.raise_for_status()
            periods = forecast.json()["properties"]["periods"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("NOAA fetch failed for %s: %s", region, exc)
        return None

    if not periods:
        return None

    now_period = periods[0]
    next_24 = periods[:24]
    temps = [p["temperature"] for p in next_24 if p.get("temperature") is not None]

    return WeatherSnapshot(
        region=region,
        location_label=label,
        temperature_f=float(now_period.get("temperature") or 0) or None,
        high_24h_f=float(max(temps)) if temps else None,
        short_forecast=now_period.get("shortForecast"),
        fetched_at=datetime.now(timezone.utc),
    )
