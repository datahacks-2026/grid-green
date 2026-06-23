"""Optional context endpoints (narrative only — not the primary carbon signal)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.models.schemas import Region
from app.config import get_settings
from app.services import heatmap, noaa_client
from app.services.limits import limiter
from app.services.regions import is_supported

router = APIRouter(prefix="/api/context", tags=["context"])
_settings = get_settings()


class WeatherResponse(BaseModel):
    region: Region
    location_label: str
    temperature_f: float | None
    high_24h_f: float | None
    short_forecast: str | None
    fetched_at: datetime


class CampusHeatResponse(BaseModel):
    source: Literal["scripps_ucsd_mobile_weather"] = "scripps_ucsd_mobile_weather"
    n_points: int
    n_stations: int
    earliest: datetime | None
    latest: datetime | None
    mean_temperature_c: float | None
    mean_relative_humidity: float | None


@router.get("/weather", response_model=WeatherResponse)
@limiter.limit(f"{_settings.rate_limit_per_minute}/minute")
def weather(
    request: Request,  # noqa: ARG001
    region: Region = "CISO",
) -> WeatherResponse:
    if not is_supported(region):
        raise HTTPException(status_code=400, detail=f"Unsupported region: {region}")
    snap = noaa_client.fetch_weather(region)
    if snap is None:
        raise HTTPException(status_code=502, detail="NOAA upstream unavailable.")
    return WeatherResponse(
        region=region,  # type: ignore[arg-type]
        location_label=snap.location_label,
        temperature_f=snap.temperature_f,
        high_24h_f=snap.high_24h_f,
        short_forecast=snap.short_forecast,
        fetched_at=snap.fetched_at,
    )


@router.get("/campus_heat", response_model=CampusHeatResponse)
@limiter.limit(f"{_settings.rate_limit_per_minute}/minute")
def campus_heat(request: Request) -> CampusHeatResponse:  # noqa: ARG001
    points = heatmap.load_csv()
    summary = heatmap.summarize(points)
    return CampusHeatResponse(
        n_points=summary.n_points,
        n_stations=summary.n_stations,
        earliest=summary.earliest,
        latest=summary.latest,
        mean_temperature_c=summary.mean_temperature_c,
        mean_relative_humidity=summary.mean_relative_humidity,
    )
