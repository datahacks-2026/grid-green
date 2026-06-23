"""Tests for sample-count scaling in the carbon estimator."""

from __future__ import annotations

from app.services.carbon_estimator import _detect_sample_count, _sample_scale_factor


def test_detect_sample_count_from_literals() -> None:
    code = "num_samples = 40000\nn_samples=2000\n"
    assert _detect_sample_count(code) == 40000


def test_sample_scale_factor_sublinear() -> None:
    assert _sample_scale_factor(10_000) == 1.0
    assert _sample_scale_factor(40_000) == 2.0
    assert _sample_scale_factor(None) == 1.0
