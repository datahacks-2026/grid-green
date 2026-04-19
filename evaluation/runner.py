from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


# Keep benchmark runs deterministic and offline-safe.
os.environ.setdefault("GRIDGREEN_DISABLE_ST", "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402


@dataclass
class Workload:
    wid: str
    group: str
    path: Path


def _load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _load_workloads(cfg: dict[str, Any], repo_root: Path) -> list[Workload]:
    workloads: list[Workload] = []
    for item in cfg.get("workloads", []):
        workloads.append(
            Workload(
                wid=item["id"],
                group=item["group"],
                path=(repo_root / item["path"]).resolve(),
            )
        )
    return workloads


def _read_code(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _pct_reduction(baseline: float, value: float) -> float:
    if baseline <= 0:
        return 0.0
    return round(((baseline - value) / baseline) * 100.0, 3)


def _safe_json(response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {}


def _estimate(client: TestClient, code: str, region: str) -> tuple[dict[str, Any], float]:
    t0 = time.perf_counter()
    r = client.post("/api/estimate_carbon", json={"code": code, "region": region})
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"/api/estimate_carbon failed ({r.status_code}) {r.text}")
    return _safe_json(r), dt


def _check_grid(client: TestClient, region: str) -> tuple[dict[str, Any], float]:
    t0 = time.perf_counter()
    r = client.get("/api/check_grid", params={"region": region})
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"/api/check_grid failed ({r.status_code}) {r.text}")
    return _safe_json(r), dt


def _clean_window(client: TestClient, region: str) -> tuple[dict[str, Any], float]:
    t0 = time.perf_counter()
    r = client.get(
        "/api/find_clean_window",
        params={"region": region, "hours_needed": 4, "max_delay_hours": 48},
    )
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"/api/find_clean_window failed ({r.status_code}) {r.text}")
    return _safe_json(r), dt


def _impact_focus_lines(estimate: dict[str, Any]) -> list[int]:
    """Match production UI: high-impact model patterns + high workload practices."""
    focus: set[int] = set()
    for p in estimate.get("detected_patterns", []):
        if p.get("impact") == "high" and p.get("line") is not None:
            focus.add(int(p["line"]))
    for w in estimate.get("workload_practices", []) or []:
        if w.get("impact") == "high" and w.get("line") is not None:
            focus.add(int(w["line"]))
    return sorted(focus)


def _suggest(
    client: TestClient,
    code: str,
    region: str,
    estimate: dict[str, Any],
    grid: dict[str, Any],
    clean: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    payload = {
        "code": code,
        "region": region,
        "co2_grams_now": estimate.get("co2_grams_now"),
        "co2_grams_optimal": estimate.get("co2_grams_optimal"),
        "current_gco2_kwh": grid.get("current_gco2_kwh"),
        "optimal_window_start": clean.get("optimal_start"),
        "co2_savings_pct_window": clean.get("co2_savings_pct"),
        "impact_focus_lines": _impact_focus_lines(estimate),
    }
    t0 = time.perf_counter()
    r = client.post("/api/suggest_greener", json=payload)
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"/api/suggest_greener failed ({r.status_code}) {r.text}")
    return _safe_json(r), dt


def _apply_all_suggestions(code: str, suggestions: list[dict[str, Any]]) -> tuple[str, bool]:
    """Apply every suggestion whose ``original_snippet`` appears in the code.

    A real user would accept all recommended swaps, not just the first. Applying
    only one caused metrics bugs (e.g. flan-t5-xxl tokenizer line swapped but
    model line left at xxl → estimator still sees the large variant).
    """
    if not suggestions:
        return code, False
    changed = False
    for s in suggestions:
        orig = s.get("original_snippet", "")
        alt = s.get("alternative_snippet", "")
        if not orig or not alt or orig == alt:
            continue
        if orig in code:
            code = code.replace(orig, alt, 1)
            changed = True
    return code, changed


def run(config_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    cfg = _load_config(config_path)
    region = cfg.get("region", "CISO")
    out_root = (repo_root / cfg.get("output_dir", "evaluation/runs")).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    workloads = _load_workloads(cfg, repo_root)
    client = TestClient(app)

    result_rows: list[dict[str, Any]] = []
    suggestion_rows: list[dict[str, Any]] = []

    for wl in workloads:
        code = _read_code(wl.path)
        status = "ok"
        err = ""

        try:
            baseline_est, t_est_base = _estimate(client, code, region)
            grid, t_grid = _check_grid(client, region)
            clean, t_clean = _clean_window(client, region)
            sugg_payload, t_suggest = _suggest(client, code, region, baseline_est, grid, clean)
            suggestions = sugg_payload.get("suggestions", [])

            swapped_code, swap_applied = _apply_all_suggestions(code, suggestions)
            swap_est, t_est_swap = _estimate(client, swapped_code, region)

            s1 = float(baseline_est.get("co2_grams_now", 0.0))
            s2 = float(swap_est.get("co2_grams_now", s1))
            s3 = float(baseline_est.get("co2_grams_optimal", s1))
            s4 = float(swap_est.get("co2_grams_optimal", s2))

            total_latency = t_est_base + t_grid + t_clean + t_suggest + t_est_swap

            for scenario, value in [
                ("S1_baseline", s1),
                ("S2_model_swap", s2),
                ("S3_time_shift", s3),
                ("S4_combined", s4),
            ]:
                result_rows.append(
                    {
                        "workload_id": wl.wid,
                        "group": wl.group,
                        "scenario": scenario,
                        "region": region,
                        "co2_grams": round(value, 3),
                        "baseline_co2_grams": round(s1, 3),
                        "reduction_pct_vs_s1": _pct_reduction(s1, value),
                        "analysis_latency_s": round(total_latency, 4),
                        "estimate_latency_s": round(t_est_base, 4),
                        "suggest_latency_s": round(t_suggest, 4),
                        "success": 1,
                        "status": "ok",
                        "error": "",
                    }
                )

            first = suggestions[0] if suggestions else {}
            suggestion_rows.append(
                {
                    "workload_id": wl.wid,
                    "group": wl.group,
                    "num_suggestions": len(suggestions),
                    "swap_applied": int(swap_applied),
                    "first_line": first.get("line"),
                    "first_carbon_saved_pct_claimed": first.get("carbon_saved_pct"),
                    "first_performance_retained_pct": first.get("performance_retained_pct"),
                    "first_original_snippet": first.get("original_snippet"),
                    "first_alternative_snippet": first.get("alternative_snippet"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            status = "error"
            err = str(exc)
            for scenario in [
                "S1_baseline",
                "S2_model_swap",
                "S3_time_shift",
                "S4_combined",
            ]:
                result_rows.append(
                    {
                        "workload_id": wl.wid,
                        "group": wl.group,
                        "scenario": scenario,
                        "region": region,
                        "co2_grams": "",
                        "baseline_co2_grams": "",
                        "reduction_pct_vs_s1": "",
                        "analysis_latency_s": "",
                        "estimate_latency_s": "",
                        "suggest_latency_s": "",
                        "success": 0,
                        "status": status,
                        "error": err,
                    }
                )
            suggestion_rows.append(
                {
                    "workload_id": wl.wid,
                    "group": wl.group,
                    "num_suggestions": 0,
                    "swap_applied": 0,
                    "first_line": "",
                    "first_carbon_saved_pct_claimed": "",
                    "first_performance_retained_pct": "",
                    "first_original_snippet": "",
                    "first_alternative_snippet": "",
                }
            )

    results_path = run_dir / "results.csv"
    suggestions_path = run_dir / "suggestions.csv"
    meta_path = run_dir / "meta.json"

    with results_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(result_rows[0].keys()))
        writer.writeheader()
        writer.writerows(result_rows)

    with suggestions_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(suggestion_rows[0].keys()))
        writer.writeheader()
        writer.writerows(suggestion_rows)

    meta = {
        "run_id": run_id,
        "region": region,
        "config_path": str(config_path),
        "workloads": len(workloads),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "results_csv": str(results_path),
        "suggestions_csv": str(suggestions_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GridGreen benchmark scenarios.")
    parser.add_argument(
        "--config",
        type=str,
        default="evaluation/configs/benchmark_config.json",
        help="Path to benchmark config JSON.",
    )
    args = parser.parse_args()

    run_dir = run(Path(args.config).resolve())
    print(f"Benchmark run complete: {run_dir}")


if __name__ == "__main__":
    main()
