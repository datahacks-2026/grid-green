"""Person B HTTP routes merged into Person A's FastAPI app."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.models.schemas import (
    GreenerSuggestion,
    ScorecardEventRequest,
    ScorecardResponse,
    SuggestGreenerRequest,
    SuggestGreenerResponse,
)
from app.services import gemini_service, rag
from app.services.session_scorecard import (
    get as scorecard_get,
    record_run_deferred,
    record_suggestion_accepted,
)

router = APIRouter(prefix="/api", tags=["model-intelligence"])


def _context_from_request(payload: SuggestGreenerRequest) -> rag.SuggestContext | None:
    if not any(
        [
            payload.region,
            payload.co2_grams_now is not None,
            payload.co2_grams_optimal is not None,
            payload.current_gco2_kwh is not None,
            payload.optimal_window_start,
            payload.co2_savings_pct_window is not None,
            payload.impact_focus_lines,
        ]
    ):
        return None
    return rag.SuggestContext(
        region=payload.region,
        co2_grams_now=payload.co2_grams_now,
        co2_grams_optimal=payload.co2_grams_optimal,
        current_gco2_kwh=payload.current_gco2_kwh,
        optimal_window_start=payload.optimal_window_start,
        co2_savings_pct_window=payload.co2_savings_pct_window,
        impact_focus_lines=tuple(payload.impact_focus_lines),
    )


@router.post("/suggest_greener", response_model=SuggestGreenerResponse)
def suggest_greener(payload: SuggestGreenerRequest) -> SuggestGreenerResponse:
    settings = get_settings()
    code = payload.code or ""
    if len(code.encode("utf-8")) > settings.max_code_bytes:
        raise HTTPException(status_code=413, detail="Code payload too large.")

    ctx = _context_from_request(payload)
    raw = rag.suggest(code, top_k=3, context=ctx)
    suggestions = [
        GreenerSuggestion(
            line=s.line,
            original_snippet=s.original_snippet,
            alternative_snippet=s.alternative_snippet,
            carbon_saved_pct=s.carbon_saved_pct,
            performance_retained_pct=s.performance_retained_pct,
            citation=s.citation,
            reasoning=gemini_service.polish_reasoning_paragraph(s.reasoning),
        )
        for s in raw
    ]
    return SuggestGreenerResponse(suggestions=suggestions)


@router.get("/scorecard", response_model=ScorecardResponse)
def scorecard(session_id: str = Query(..., min_length=1)) -> ScorecardResponse:
    return scorecard_get(session_id)


@router.post("/scorecard/event", response_model=ScorecardResponse)
def scorecard_event(body: ScorecardEventRequest) -> ScorecardResponse:
    saved = float(body.co2_saved_grams or 0.0)
    if body.event == "suggestion_accepted":
        return record_suggestion_accepted(body.session_id, saved)
    return record_run_deferred(body.session_id, saved)
