"""Pydantic models matching the locked API contract in README §5."""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


Region = Literal["CISO", "ERCO", "PJM", "MISO", "NYIS"]


class SuggestRequest(BaseModel):
    code: str = Field(..., description="Raw user source code to analyze.")


class Suggestion(BaseModel):
    line: int
    original_snippet: str
    alternative_snippet: str
    carbon_saved_pct: int
    performance_retained_pct: int
    citation: str
    reasoning: str


class SuggestResponse(BaseModel):
    suggestions: List[Suggestion]


class Scorecard(BaseModel):
    co2_saved_grams: int = 0
    runs_deferred: int = 0
    suggestions_accepted: int = 0


class ScorecardEvent(BaseModel):
    """POSTed by the frontend whenever the user accepts a suggestion or defers a run."""
    session_id: str
    event: Literal["suggestion_accepted", "run_deferred"]
    co2_saved_grams: Optional[int] = 0
