"""Routes shared with Person B's slice.

- `POST /api/suggest_greener` — **real** in Person A's slice via the RAG
  index (`app/services/rag.py`). Person B layers Gemini NL reasoning on
  top of these suggestions in their own service; the JSON shape stays
  the same so this can be swapped in without touching the frontend.
- `GET /api/scorecard` — owned by Person B; left as a contract-valid stub.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.models.schemas import (
    GreenerSuggestion,
    ScorecardResponse,
    SuggestGreenerRequest,
    SuggestGreenerResponse,
)
from app.services import rag

router = APIRouter(prefix="/api", tags=["model-intelligence"])


@router.post("/suggest_greener", response_model=SuggestGreenerResponse)
def suggest_greener(payload: SuggestGreenerRequest) -> SuggestGreenerResponse:
    settings = get_settings()
    code = payload.code or ""
    if len(code.encode("utf-8")) > settings.max_code_bytes:
        raise HTTPException(status_code=413, detail="Code payload too large.")

    suggestions = rag.suggest(code, top_k=3)
    return SuggestGreenerResponse(
        suggestions=[
            GreenerSuggestion(
                line=s.line,
                original_snippet=s.original_snippet,
                alternative_snippet=s.alternative_snippet,
                carbon_saved_pct=s.carbon_saved_pct,
                performance_retained_pct=s.performance_retained_pct,
                citation=s.citation,
                reasoning=s.reasoning,
            )
            for s in suggestions
        ]
    )


@router.get("/scorecard", response_model=ScorecardResponse)
def scorecard(session_id: str = Query(..., min_length=1)) -> ScorecardResponse:
    # Person B replaces this with real session aggregation.
    return ScorecardResponse(co2_saved_grams=0.0, runs_deferred=0, suggestions_accepted=0)
