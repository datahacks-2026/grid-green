"""Shared helpers for grid-aware carbon estimation."""

from __future__ import annotations

import math


def hours_needed_from_estimate(compute_hours: float) -> int:
    """Map estimated run duration to clean-window search bounds (1–24 h)."""
    if not math.isfinite(compute_hours) or compute_hours <= 0:
        return 1
    return max(1, min(24, math.ceil(compute_hours)))
