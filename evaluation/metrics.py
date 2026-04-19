from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _df_to_markdown(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = []
    for _, row in df.iterrows():
        vals = []
        for c in df.columns:
            v = row[c]
            vals.append("" if pd.isna(v) else str(v))
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join([header, sep, *rows])


def _load(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    results = pd.read_csv(run_dir / "results.csv")
    suggestions = pd.read_csv(run_dir / "suggestions.csv")
    return results, suggestions


def _to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _table1_system(results: pd.DataFrame) -> pd.DataFrame:
    rr = _to_numeric(results, ["analysis_latency_s", "success"])
    return pd.DataFrame(
        [
            {
                "system": "GridGreen",
                "code_level_swap_suggestions": "Yes",
                "time_shift_recommendation": "Yes",
                "runtime_telemetry": "No",
                "mean_analysis_latency_s": round(rr["analysis_latency_s"].mean(skipna=True), 4),
                "success_rate_pct": round(rr["success"].mean(skipna=True) * 100.0, 2),
            },
            {
                "system": "CodeCarbon",
                "code_level_swap_suggestions": "No",
                "time_shift_recommendation": "Partial",
                "runtime_telemetry": "Yes",
                "mean_analysis_latency_s": "N/A",
                "success_rate_pct": "N/A",
            },
            {
                "system": "CarbonTracker",
                "code_level_swap_suggestions": "No",
                "time_shift_recommendation": "Partial",
                "runtime_telemetry": "Yes",
                "mean_analysis_latency_s": "N/A",
                "success_rate_pct": "N/A",
            },
        ]
    )


def _table2_reductions(results: pd.DataFrame) -> pd.DataFrame:
    rr = _to_numeric(results, ["reduction_pct_vs_s1"])
    pivot = (
        rr[rr["scenario"].isin(["S2_model_swap", "S3_time_shift", "S4_combined"])]
        .groupby(["group", "scenario"], dropna=False)["reduction_pct_vs_s1"]
        .mean()
        .unstack(fill_value=0.0)
        .reset_index()
        .rename(
            columns={
                "group": "workload_group",
                "S2_model_swap": "S2_model_swap_only_pct",
                "S3_time_shift": "S3_time_shift_only_pct",
                "S4_combined": "S4_combined_pct",
            }
        )
    )
    overall = (
        rr[rr["scenario"].isin(["S2_model_swap", "S3_time_shift", "S4_combined"])]
        .groupby("scenario", dropna=False)["reduction_pct_vs_s1"]
        .mean()
        .to_dict()
    )
    overall_row = pd.DataFrame(
        [
            {
                "workload_group": "overall",
                "S2_model_swap_only_pct": round(overall.get("S2_model_swap", 0.0), 3),
                "S3_time_shift_only_pct": round(overall.get("S3_time_shift", 0.0), 3),
                "S4_combined_pct": round(overall.get("S4_combined", 0.0), 3),
            }
        ]
    )
    cols = [
        "workload_group",
        "S2_model_swap_only_pct",
        "S3_time_shift_only_pct",
        "S4_combined_pct",
    ]
    out = pd.concat([pivot[cols], overall_row[cols]], ignore_index=True)
    for c in ("S2_model_swap_only_pct", "S3_time_shift_only_pct", "S4_combined_pct"):
        out[c] = pd.to_numeric(out[c], errors="coerce").round(2)
    return out


def _table3_accuracy(results: pd.DataFrame) -> pd.DataFrame:
    # Extension point: populate `observed_co2_grams` in results.csv for real-run validation.
    rr = _to_numeric(results, ["co2_grams"])
    if "observed_co2_grams" not in rr.columns:
        return pd.DataFrame(
            [
                {
                    "method": "GridGreen",
                    "mae_gco2e": "N/A",
                    "mape_pct": "N/A",
                    "r2": "N/A",
                    "median_runtime_overhead_pct": "N/A",
                }
            ]
        )
    rr["observed_co2_grams"] = pd.to_numeric(rr["observed_co2_grams"], errors="coerce")
    rr = rr.dropna(subset=["co2_grams", "observed_co2_grams"])
    if rr.empty:
        return pd.DataFrame(
            [
                {
                    "method": "GridGreen",
                    "mae_gco2e": "N/A",
                    "mape_pct": "N/A",
                    "r2": "N/A",
                    "median_runtime_overhead_pct": "N/A",
                }
            ]
        )
    abs_err = (rr["co2_grams"] - rr["observed_co2_grams"]).abs()
    mae = abs_err.mean()
    mape = ((abs_err / rr["observed_co2_grams"].clip(lower=1e-9)) * 100.0).mean()
    return pd.DataFrame(
        [
            {
                "method": "GridGreen",
                "mae_gco2e": round(float(mae), 4),
                "mape_pct": round(float(mape), 4),
                "r2": "N/A",
                "median_runtime_overhead_pct": "N/A",
            }
        ]
    )


def _table4_suggestion_quality(suggestions: pd.DataFrame) -> pd.DataFrame:
    ss = _to_numeric(
        suggestions,
        ["num_suggestions", "swap_applied", "first_carbon_saved_pct_claimed"],
    )
    any_suggestion_rate = (ss["num_suggestions"] > 0).mean() * 100.0
    accepted = ss["swap_applied"].mean() * 100.0
    avg_claimed = ss["first_carbon_saved_pct_claimed"].mean(skipna=True)
    return pd.DataFrame(
        [
            {
                "system": "GridGreen",
                "workloads_with_any_suggestion_pct": round(float(any_suggestion_rate), 3),
                "first_swap_text_apply_success_pct": round(float(accepted), 3),
                "avg_claimed_compute_reduction_pct": round(float(avg_claimed), 2)
                if pd.notna(avg_claimed)
                else "N/A",
            }
        ]
    )


def _write_report(run_dir: Path, t1: pd.DataFrame, t2: pd.DataFrame, t3: pd.DataFrame, t4: pd.DataFrame) -> None:
    lines = [
        "# Benchmark Report",
        "",
        "## Methodology",
        "",
        "All CO2 estimates are **rules-based** -- derived from static code analysis,",
        "a curated model catalog, and published scaling laws (Patterson et al. 2022,",
        "Kaplan et al. 2020, Strubell et al. 2019). They assume A100-80GB @ 400W TDP.",
        "`carbon_saved_pct` in suggestions is the parameter-ratio compute reduction",
        "(1 - params_to/params_from), not a metered energy delta.",
        "",
        "## Table 1. System-level comparison",
        "",
        _df_to_markdown(t1),
        "",
        "## Table 2. Estimated CO2 reduction by scenario (relative to S1)",
        "",
        _df_to_markdown(t2),
        "",
        "_Percent change in **estimated** script CO2 vs scenario S1 (run-now, same code). "
        "**Negative** S3/S4 values mean the optimal-window forecast intensity was "
        "**higher** than the current snapshot for that workload group -- this depends "
        "on the grid state at benchmark time and is expected._",
        "",
        "## Table 3. Estimation accuracy vs observed runs",
        "",
        _df_to_markdown(t3),
        "",
        "_N/A = no ground-truth runtime measurements available. Populate "
        "`observed_co2_grams` (e.g. via CodeCarbon) to generate MAE / MAPE._",
        "",
        "## Table 4. Suggestion coverage (harness)",
        "",
        _df_to_markdown(t4),
        "",
        "_`workloads_with_any_suggestion_pct` = share of workloads where `suggest_greener` returned >=1 suggestion. "
        "`first_swap_text_apply_success_pct` = share where the harness successfully applied all "
        "suggestions to the source text. `avg_claimed_compute_reduction_pct` is the mean parameter-ratio "
        "savings from the first suggestion -- not a measured energy reduction._",
        "",
    ]
    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run(run_dir: Path) -> None:
    results, suggestions = _load(run_dir)
    t1 = _table1_system(results)
    t2 = _table2_reductions(results)
    t3 = _table3_accuracy(results)
    t4 = _table4_suggestion_quality(suggestions)

    t1.to_csv(run_dir / "table1_system_comparison.csv", index=False)
    t2.to_csv(run_dir / "table2_reductions.csv", index=False)
    t3.to_csv(run_dir / "table3_accuracy.csv", index=False)
    t4.to_csv(run_dir / "table4_suggestion_quality.csv", index=False)
    _write_report(run_dir, t1, t2, t3, t4)

    print(f"Wrote tables and report to: {run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate benchmark tables from a run directory.")
    parser.add_argument(
        "--run-dir",
        required=True,
        type=str,
        help="Path like evaluation/runs/<timestamp>.",
    )
    args = parser.parse_args()
    run(Path(args.run_dir).resolve())


if __name__ == "__main__":
    main()
