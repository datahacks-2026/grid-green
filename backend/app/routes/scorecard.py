"""Scorecard endpoints — read + record events."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import Scorecard, ScorecardEvent
from app.services import scorecard_store

router = APIRouter(tags=["scorecard"])


@router.get("/scorecard", response_model=Scorecard)
def read_scorecard(session_id: str = Query(..., min_length=1)) -> Scorecard:
    return scorecard_store.get(session_id)


@router.post("/scorecard/event", response_model=Scorecard)
def record_event(event: ScorecardEvent) -> Scorecard:
    saved = event.co2_saved_grams or 0
    if event.event == "suggestion_accepted":
        return scorecard_store.record_suggestion_accepted(event.session_id, saved)
    return scorecard_store.record_run_deferred(event.session_id, saved)
