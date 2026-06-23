"""Tests for optional CodeCarbon telemetry merge."""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

from telemetry.codecarbon_adapter import (
    load_observed_co2_grams,
    merge_into_result_rows,
)


def test_load_observed_co2_grams_from_codecarbon_csv() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        observed = root / "emissions.csv"
        observed.write_text(
            "project_name,emissions\nllm_flan_xxl,0.42\n",
            encoding="utf-8",
        )
        mapping = root / "map.json"
        mapping.write_text(
            json.dumps({"project_to_workload": {"llm_flan_xxl": "llm_flan_xxl"}}),
            encoding="utf-8",
        )
        out = load_observed_co2_grams(observed_csv=observed, map_path=mapping)
        assert out["llm_flan_xxl"] == 420.0


def test_merge_into_result_rows_only_s1() -> None:
    rows = [
        {"workload_id": "llm_flan_xxl", "scenario": "S1_baseline", "co2_grams": 100.0},
        {"workload_id": "llm_flan_xxl", "scenario": "S2_model_swap", "co2_grams": 50.0},
    ]
    merged = merge_into_result_rows(rows, {"llm_flan_xxl": 420.0})
    assert merged[0]["observed_co2_grams"] == 420.0
    assert "observed_co2_grams" not in merged[1]
