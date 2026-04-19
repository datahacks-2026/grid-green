"""Grid-intelligence endpoints (Person A's slice).

- GET /api/check_grid
- GET /api/find_clean_window
- POST /api/estimate_carbon
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.config import get_settings
from app.models.schemas import (
    CheckGridResponse,
    DetectedPattern,
    EstimateCarbonRequest,
    EstimateCarbonResponse,
    FindCleanWindowResponse,
    ForecastPoint,
    Region,
    WorkloadPractice,
)
from app.services import carbon_estimator, forecaster
from app.services.limits import limiter
from app.services.regions import is_supported

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["grid"])

_settings = get_settings()


@router.get("/check_grid", response_model=CheckGridResponse)
@limiter.limit(f"{_settings.rate_limit_per_minute}/minute")
def check_grid(request: Request, region: Region = "CISO") -> CheckGridResponse:  # noqa: ARG001
    if not is_supported(region):
        raise HTTPException(status_code=400, detail=f"Unsupported region: {region}")
    ts, value = forecaster.latest_intensity(region)
    return CheckGridResponse(
        region=region,
        current_gco2_kwh=round(value, 2),
        trend=forecaster.trend(region),
        last_updated=ts.astimezone(timezone.utc),
    )


@router.get("/find_clean_window", response_model=FindCleanWindowResponse)
@limiter.limit(f"{_settings.rate_limit_per_minute}/minute")
def find_clean_window(
    request: Request,  # noqa: ARG001 — required by slowapi
    region: Region = "CISO",
    hours_needed: Annotated[int, Query(ge=1, le=24)] = 4,
    max_delay_hours: Annotated[int, Query(ge=1, le=48)] = 48,
) -> FindCleanWindowResponse:
    if not is_supported(region):
        raise HTTPException(status_code=400, detail=f"Unsupported region: {region}")

    optimal_start, expected, current, savings, forecast = forecaster.find_clean_window(
        region=region,
        hours_needed=hours_needed,
        max_delay_hours=max_delay_hours,
    )
    return FindCleanWindowResponse(
        optimal_start=optimal_start.astimezone(timezone.utc),
        expected_gco2_kwh=expected,
        current_gco2_kwh=round(current, 2),
        co2_savings_pct=savings,
        forecast_48h=[
            ForecastPoint(hour=ts.astimezone(timezone.utc), gco2_kwh=round(v, 2))
            for ts, v in forecast
        ],
    )


@router.post("/estimate_carbon", response_model=EstimateCarbonResponse)
@limiter.limit(f"{_settings.rate_limit_per_minute}/minute")
def estimate_carbon(
    request: Request,  # noqa: ARG001
    payload: EstimateCarbonRequest,
) -> EstimateCarbonResponse:
    settings = get_settings()
    code = payload.code or ""
    if len(code.encode("utf-8")) > settings.max_code_bytes:
        raise HTTPException(status_code=413, detail="Code payload too large.")
    if not is_supported(payload.region):
        raise HTTPException(status_code=400, detail=f"Unsupported region: {payload.region}")

    _, current = forecaster.latest_intensity(payload.region)
    _, optimal_expected, _, _, _ = forecaster.find_clean_window(
        region=payload.region, hours_needed=4, max_delay_hours=48
    )
    result = carbon_estimator.estimate(
        code,
        current_gco2_kwh=current,
        optimal_gco2_kwh=optimal_expected,
    )
    return EstimateCarbonResponse(
        co2_grams_now=result.co2_grams_now,
        co2_grams_optimal=result.co2_grams_optimal,
        gpu_hours=result.gpu_hours,
        kwh_estimated=result.kwh_estimated,
        confidence=result.confidence,
        detected_patterns=[
            DetectedPattern(line=p.line, pattern=p.pattern, impact=p.impact)  # type: ignore[arg-type]
            for p in result.detected_patterns
        ],
        workload_practices=[
            WorkloadPractice(
                id=w.id,
                line=w.line,
                label=w.label,
                impact=w.impact,  # type: ignore[arg-type]
                rationale=w.rationale,
            )
            for w in result.workload_practices
        ],
    )
