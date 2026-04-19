"""POST /api/suggest_greener — model swap suggestions with NL reasoning."""
from __future__ import annotations

from fastapi import APIRouter

from app.schemas import SuggestRequest, SuggestResponse, Suggestion
from app.services import gemini_service, rag_service

router = APIRouter(tags=["model-intelligence"])


@router.post("/suggest_greener", response_model=SuggestResponse)
def suggest_greener(req: SuggestRequest) -> SuggestResponse:
    matches = rag_service.detect_models(req.code)

    suggestions = [
        Suggestion(
            line=m.line,
            original_snippet=m.original_snippet,
            alternative_snippet=m.alternative_snippet,
            carbon_saved_pct=m.carbon_saved_pct,
            performance_retained_pct=m.performance_retained_pct,
            citation=m.citation,
            reasoning=gemini_service.explain_alternative(
                original_model=_extract_name(m.original_snippet),
                alternative_model=_extract_name(m.alternative_snippet),
                carbon_saved_pct=m.carbon_saved_pct,
                performance_retained_pct=m.performance_retained_pct,
                citation=m.citation,
            ),
        )
        for m in matches
    ]
    return SuggestResponse(suggestions=suggestions)


def _extract_name(snippet: str) -> str:
    for quote in ("'", '"'):
        if quote in snippet:
            return snippet.split(quote)[1]
    return snippet
