"""Pydantic schemas mirroring CONTRACT.md."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, Field

Region = Literal["CISO", "ERCO", "PJM", "MISO", "NYIS"]
Impact = Literal["low", "medium", "high"]
Confidence = Literal["low", "medium", "high"]
Trend = Literal["rising", "falling", "flat"]


class DetectedPattern(BaseModel):
    line: int
    pattern: str
    impact: Impact


class EstimateCarbonRequest(BaseModel):
    code: str = Field(..., description="Pasted training script.")
    region: Region = "CISO"


class EstimateCarbonResponse(BaseModel):
    co2_grams_now: float
    co2_grams_optimal: float
    gpu_hours: float
    kwh_estimated: float
    confidence: Confidence
    detected_patterns: List[DetectedPattern]


class CheckGridResponse(BaseModel):
    region: Region
    current_gco2_kwh: float
    trend: Trend
    last_updated: datetime


class ForecastPoint(BaseModel):
    hour: datetime
    gco2_kwh: float


class FindCleanWindowResponse(BaseModel):
    optimal_start: datetime
    expected_gco2_kwh: float
    current_gco2_kwh: float
    co2_savings_pct: float
    forecast_48h: List[ForecastPoint]


# Person B owns these — included so Person A's MCP/HTTP tooling can stub them
# without breaking shapes.
class SuggestGreenerRequest(BaseModel):
    """`code` is required; all other fields come from Part A after the user runs analysis."""

    code: str
    region: Region | None = Field(
        default=None,
        description="Balancing authority — used to tailor grid-aware reasoning.",
    )
    co2_grams_now: float | None = Field(
        default=None, description="From POST /api/estimate_carbon — run-now script estimate."
    )
    co2_grams_optimal: float | None = Field(
        default=None, description="From estimate_carbon — aligned with cleaner forecast window."
    )
    current_gco2_kwh: float | None = Field(
        default=None, description="From GET /api/check_grid — live grid carbon intensity."
    )
    optimal_window_start: str | None = Field(
        default=None,
        description="ISO-8601 UTC from find_clean_window.optimal_start.",
    )
    co2_savings_pct_window: float | None = Field(
        default=None,
        description="From find_clean_window.co2_savings_pct — deferral benefit on intensity.",
    )
    impact_focus_lines: List[int] = Field(
        default_factory=list,
        description="Line numbers of high-impact patterns from estimate_carbon.detected_patterns.",
    )


class GreenerSuggestion(BaseModel):
    line: int
    original_snippet: str
    alternative_snippet: str
    carbon_saved_pct: float
    performance_retained_pct: float
    citation: str
    reasoning: str


class SuggestGreenerResponse(BaseModel):
    suggestions: List[GreenerSuggestion]


class ScorecardResponse(BaseModel):
    co2_saved_grams: float
    runs_deferred: int
    suggestions_accepted: int


class ScorecardEventRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    event: Literal["suggestion_accepted", "run_deferred"]
    co2_saved_grams: float | None = 0.0
