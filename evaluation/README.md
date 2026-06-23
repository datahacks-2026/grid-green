# Evaluation Harness

Reproducible benchmark scaffold for GridGreen.

## Scenarios

Each workload runs four scenarios:

| ID | Description |
|---|---|
| S1 | Baseline (original code, run-now estimate) |
| S2 | Model swap applied, run-now estimate |
| S3 | Original code, optimal-window estimate |
| S4 | Combined swap + optimal window |

## Standard benchmark (12 workloads)

```bash
python -m evaluation.runner --config evaluation/configs/benchmark_config.json
python -m evaluation.metrics --run-dir evaluation/runs/<timestamp>
```

## Ground-truth validation (CodeCarbon)

Nine self-contained runnable workloads live under `evaluation/workloads/runnable/` (six CPU sklearn, three Hugging Face fine-tunes). They mirror benchmark patterns but execute real training on synthetic data. GPU workloads use `torch` and `transformers`; without CUDA they fall back to CPU.

### 1. Install telemetry extras

```bash
pip install -r evaluation/requirements-telemetry.txt
```

### 2. Capture observed emissions

```bash
python -m evaluation.telemetry.run_codecarbon
```

Writes `evaluation/telemetry/observed_emissions.csv` (kg CO₂ per workload).

### 3. Run validation benchmark

```bash
python -m evaluation.runner --config evaluation/configs/telemetry_benchmark_config.json
python -m evaluation.metrics --run-dir evaluation/runs/<timestamp>
```

Or run the full pipeline:

```bash
python -m evaluation.telemetry.baseline_report
```

### 4. Read Table 3 (accuracy)

`metrics.py` produces `table3_accuracy.csv` with MAE and MAPE when `observed_co2_grams` is present in `results.csv` (S1 rows only).

| Column | Meaning |
|---|---|
| `mae_gco2e` | Mean absolute error (grams CO₂) vs CodeCarbon |
| `mape_pct` | Mean absolute percentage error |

`baseline_comparison.csv` in the run directory lists per-workload errors.

## Outputs

Each run directory contains:

- `results.csv`, `suggestions.csv`, `meta.json`
- `table1_system_comparison.csv` through `table4_suggestion_quality.csv`
- `report.md`

## Notes

- The harness uses FastAPI `TestClient` (no live server).
- `GRIDGREEN_DISABLE_ST=1` is set for deterministic offline runs.
- Without CodeCarbon installed, `run_codecarbon` uses a CPU-time proxy (suitable for CI smoke tests only; use real CodeCarbon for paper numbers).
