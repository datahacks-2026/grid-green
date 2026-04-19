"""In-memory scorecard for GET/POST /api/scorecard (Person B contract)."""

from __future__ import annotations

from threading import Lock

from app.models.schemas import ScorecardResponse

_lock = Lock()
_store: dict[str, ScorecardResponse] = {}


def get(session_id: str) -> ScorecardResponse:
    with _lock:
        return _store.get(
            session_id,
            ScorecardResponse(co2_saved_grams=0.0, runs_deferred=0, suggestions_accepted=0),
        ).model_copy()


def record_suggestion_accepted(session_id: str, co2_saved_grams: float) -> ScorecardResponse:
    with _lock:
        cur = _store.setdefault(
            session_id,
            ScorecardResponse(co2_saved_grams=0.0, runs_deferred=0, suggestions_accepted=0),
        )
        cur.suggestions_accepted += 1
        cur.co2_saved_grams += max(0.0, co2_saved_grams)
        return cur.model_copy()


def record_run_deferred(session_id: str, co2_saved_grams: float) -> ScorecardResponse:
    with _lock:
        cur = _store.setdefault(
            session_id,
            ScorecardResponse(co2_saved_grams=0.0, runs_deferred=0, suggestions_accepted=0),
        )
        cur.runs_deferred += 1
        cur.co2_saved_grams += max(0.0, co2_saved_grams)
        return cur.model_copy()
