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
    code: str


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
