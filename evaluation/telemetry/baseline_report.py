"""End-to-end telemetry validation and baseline comparison report."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_CONFIG = REPO_ROOT / "evaluation" / "configs" / "telemetry_benchmark_config.json"
OBSERVED_CSV = REPO_ROOT / "evaluation" / "telemetry" / "observed_emissions.csv"


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)


def run_validation(skip_codecarbon: bool = False) -> Path:
    if not skip_codecarbon:
        _run([sys.executable, "-m", "evaluation.telemetry.run_codecarbon"])
    if not OBSERVED_CSV.is_file():
        raise FileNotFoundError(f"Missing observed emissions: {OBSERVED_CSV}")

    _run(
        [
            sys.executable,
            "-m",
            "evaluation.runner",
            "--config",
            str(TELEMETRY_CONFIG),
        ]
    )
    runs = sorted((REPO_ROOT / "evaluation" / "runs").glob("*/results.csv"))
    if not runs:
        raise RuntimeError("No benchmark run directory found")
    run_dir = runs[-1].parent

    _run([sys.executable, "-m", "evaluation.metrics", "--run-dir", str(run_dir)])

    results = pd.read_csv(run_dir / "results.csv")
    s1 = results[results["scenario"] == "S1_baseline"].copy()
    if "observed_co2_grams" not in s1.columns:
        raise RuntimeError("observed_co2_grams column missing; run CodeCarbon capture first")

    s1["observed_co2_grams"] = pd.to_numeric(s1["observed_co2_grams"], errors="coerce")
    s1["co2_grams"] = pd.to_numeric(s1["co2_grams"], errors="coerce")
    valid = s1.dropna(subset=["observed_co2_grams", "co2_grams"])
    valid = valid[valid["observed_co2_grams"] > 0.0001]
    if valid.empty:
        raise RuntimeError("No rows with both estimated and observed CO2")

    valid["abs_error"] = (valid["co2_grams"] - valid["observed_co2_grams"]).abs()
    valid["ape_pct"] = (
        valid["abs_error"] / valid["observed_co2_grams"].clip(lower=1e-9) * 100.0
    )

    summary = pd.DataFrame(
        [
            {
                "workloads": len(valid),
                "mae_gco2e": round(valid["abs_error"].mean(), 4),
                "mape_pct": round(valid["ape_pct"].mean(), 2),
                "median_ape_pct": round(valid["ape_pct"].median(), 2),
            }
        ]
    )

    out_dir = run_dir
    per_workload = valid[
        ["workload_id", "co2_grams", "observed_co2_grams", "abs_error", "ape_pct"]
    ].sort_values("workload_id")
    per_workload.to_csv(out_dir / "baseline_comparison.csv", index=False)
    summary.to_csv(out_dir / "baseline_summary.csv", index=False)

    print("\n=== Baseline validation summary ===")
    print(summary.to_string(index=False))
    print(f"\nWrote {out_dir / 'baseline_comparison.csv'}")
    print(f"Report: {out_dir / 'report.md'}")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run telemetry validation and baseline report.")
    parser.add_argument(
        "--skip-codecarbon",
        action="store_true",
        help="Reuse existing observed_emissions.csv",
    )
    args = parser.parse_args()
    run_validation(skip_codecarbon=args.skip_codecarbon)


if __name__ == "__main__":
    main()
