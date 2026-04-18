"""In-memory scorecard keyed by session_id.

Hackathon-grade — single process, lost on restart. If we have time in
Phase 6, we can swap the dict for a Snowflake table without touching
the route signature.
"""
from __future__ import annotations

from threading import Lock
from typing import Dict

from app.schemas import Scorecard


_lock = Lock()
_store: Dict[str, Scorecard] = {}


def get(session_id: str) -> Scorecard:
    with _lock:
        return _store.get(session_id, Scorecard()).model_copy()


def record_suggestion_accepted(session_id: str, co2_saved_grams: int) -> Scorecard:
    with _lock:
        card = _store.setdefault(session_id, Scorecard())
        card.suggestions_accepted += 1
        card.co2_saved_grams += max(0, co2_saved_grams)
        return card.model_copy()


def record_run_deferred(session_id: str, co2_saved_grams: int) -> Scorecard:
    with _lock:
        card = _store.setdefault(session_id, Scorecard())
        card.runs_deferred += 1
        card.co2_saved_grams += max(0, co2_saved_grams)
        return card.model_copy()
