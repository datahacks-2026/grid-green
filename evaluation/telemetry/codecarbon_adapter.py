"""Load observed CO2 measurements from CodeCarbon emission CSV exports.

CodeCarbon writes ``emissions.csv`` with columns including ``project_name`` and
``emissions`` (kg CO2). Map ``project_name`` to GridGreen ``workload_id`` values
via ``evaluation/configs/telemetry_map.json``.

Usage:
    1. Run workloads instrumented with CodeCarbon; export emissions.csv.
    2. Copy or symlink to ``evaluation/telemetry/observed_emissions.csv``.
    3. Run the benchmark: observed values merge into ``results.csv`` for MAE/MAPE.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OBSERVED = Path(__file__).resolve().parent / "observed_emissions.csv"
DEFAULT_MAP = REPO_ROOT / "evaluation" / "configs" / "telemetry_map.json"


def _load_map(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in (data.get("project_to_workload") or {}).items()}


def load_observed_co2_grams(
    observed_csv: Path | None = None,
    map_path: Path | None = None,
) -> dict[str, float]:
    """Return workload_id → observed CO2 in grams (S1 baseline runs only)."""
    observed_csv = observed_csv or DEFAULT_OBSERVED
    map_path = map_path or DEFAULT_MAP
    if not observed_csv.is_file():
        return {}

    project_to_workload = _load_map(map_path)
    out: dict[str, float] = {}

    with observed_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            project = (row.get("project_name") or row.get("run_id") or "").strip()
            if not project:
                continue
            workload_id = project_to_workload.get(project, project)
            raw = row.get("emissions") or row.get("emissions_kg") or row.get("co2_grams")
            if raw is None or str(raw).strip() == "":
                continue
            value = float(raw)
            # CodeCarbon reports kg; convert unless column already says grams.
            if "co2_grams" not in (row.keys()):
                value *= 1000.0
            out[workload_id] = value

    return out


def merge_into_result_rows(
    result_rows: list[dict[str, Any]],
    observed: dict[str, float],
) -> list[dict[str, Any]]:
    """Attach ``observed_co2_grams`` to S1_baseline rows when telemetry exists."""
    merged: list[dict[str, Any]] = []
    for row in result_rows:
        copy = dict(row)
        if (
            copy.get("scenario") == "S1_baseline"
            and copy.get("workload_id") in observed
        ):
            copy["observed_co2_grams"] = round(observed[copy["workload_id"]], 3)
        merged.append(copy)
    return merged
