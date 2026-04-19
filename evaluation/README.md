# Evaluation Harness

This folder provides a reproducible benchmark scaffold for GridGreen.

It runs four scenarios per workload:

- `S1`: baseline (original code, run-now estimate)
- `S2`: model-swap only (first suggestion applied, run-now estimate)
- `S3`: time-shift only (original code, optimal-window estimate)
- `S4`: combined (first suggestion applied, optimal-window estimate)

## Quickstart

From repo root:

```bash
./.venv/bin/python evaluation/runner.py --config evaluation/configs/benchmark_config.json
./.venv/bin/python evaluation/metrics.py --run-dir evaluation/runs/<timestamp>
```

`runner.py` writes raw outputs into:

- `evaluation/runs/<timestamp>/results.csv`
- `evaluation/runs/<timestamp>/suggestions.csv`
- `evaluation/runs/<timestamp>/meta.json`

`metrics.py` writes:

- `evaluation/runs/<timestamp>/table1_system_comparison.csv`
- `evaluation/runs/<timestamp>/table2_reductions.csv`
- `evaluation/runs/<timestamp>/table3_accuracy.csv` (when observed values exist)
- `evaluation/runs/<timestamp>/table4_suggestion_quality.csv`
- `evaluation/runs/<timestamp>/report.md`

Table 4 column **`workloads_with_any_suggestion_pct`** is the fraction of workloads with
at least one suggestion (harness coverage), **not** NLP precision@k. **`first_swap_text_apply_success_pct`**
is whether the first snippet could be string-replaced into the synthetic code.

## Notes

- The harness uses FastAPI `TestClient` (no live server needed).
- It sets `GRIDGREEN_DISABLE_ST=1` for deterministic, offline-safe runs.
- Optional external tools (CodeCarbon / CarbonTracker) are modeled as extension points in config but not executed by default.
