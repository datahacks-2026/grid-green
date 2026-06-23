"""Tests for shared grid estimation helpers."""

from __future__ import annotations

from app.services.grid_helpers import hours_needed_from_estimate


def test_hours_needed_from_estimate_clamps() -> None:
    assert hours_needed_from_estimate(0.2) == 1
    assert hours_needed_from_estimate(4.1) == 5
    assert hours_needed_from_estimate(100.0) == 24
    assert hours_needed_from_estimate(float("nan")) == 1
