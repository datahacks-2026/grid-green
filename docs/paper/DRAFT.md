# GridGreen: A Pre-Execution Carbon Copilot for ML Training

Draft outline for workshop submission. Replace bracketed values after running `evaluation/telemetry/baseline_report.py`.

## Abstract

Machine learning engineers often commit GPU hours before understanding the carbon cost of a training script. We present GridGreen, a system that estimates CO₂ emissions from static code analysis, recommends smaller model alternatives with benchmark citations, and identifies low-carbon grid windows using US EIA data. GridGreen is available as a web application and as an MCP tool server for coding agents. On five CPU workloads with measurable CodeCarbon emissions, static estimates achieve 0.20 gCO₂e MAE (MAPE is inflated when observed emissions approach zero). Three additional GPU-oriented workloads (`distilgpt2`, `flan-t5-small`, `distilbert-base-uncased`) exercise the `from_pretrained` path under CodeCarbon; run `baseline_report` on CUDA hardware to populate Table 3 GPU rows. Combined mitigation scenarios reduce estimated LLM emissions by 50.4% (S4 vs S1 overall).

## 1. Introduction

- Motivation: training emissions are opaque at edit time
- Gap: runtime trackers vs manual calculators
- Contributions: integrated copilot, curated RAG corpus, evaluation harness with telemetry validation, MCP interface

## 2. Related Work

See [RELATED_WORK.md](./RELATED_WORK.md).

## 3. System Design

- FastAPI backend: `carbon_estimator`, `rag`, `forecaster`, `session_scorecard`
- Next.js frontend with Monaco editor
- MCP server (`backend/mcp_server.py`) with stdio and SSE transports

## 4. Methodology

- AST + regex model detection
- Scaling laws (Patterson 2022, Kaplan 2020, Strubell 2019)
- Dataset-size heuristics from `num_samples` / `n_samples` literals
- EIA grid intensity for five US balancing authorities
- Limitations stated in API `methodology` field

## 5. Evaluation

### 5.1 Harness scenarios

| Scenario | Description |
|---|---|
| S1 | Baseline code, run-now intensity |
| S2 | Model swap applied, run-now |
| S3 | Original code, optimal window intensity |
| S4 | Model swap + optimal window |

### 5.2 Accuracy vs CodeCarbon

Nine runnable workloads (six CPU sklearn, three HF GPU/CPU fine-tunes) live under `evaluation/workloads/runnable/`. GPU workloads require `torch` and `transformers` from `evaluation/requirements-telemetry.txt`; first run downloads model weights from Hugging Face.

Run:

```bash
pip install -r evaluation/requirements-telemetry.txt
python -m evaluation.telemetry.baseline_report
```

Record Table 3 and `baseline_summary.csv` from the latest `evaluation/runs/<timestamp>/` directory. CPU-only hosts still execute GPU workloads on CPU (slower, lower absolute emissions).

### 5.3 Suggestion coverage

Report `workloads_with_any_suggestion_pct` from Table 4 of the benchmark report.

### 5.4 Latency

Mean analysis latency from Table 1 ([value] ms in-process).

## 6. Discussion

- When static analysis succeeds (sklearn, explicit `from_pretrained`)
- Failure modes: custom classes, closed APIs, missing dataset literals
- Catalog bias and region coverage (5 BAs)

## 7. Conclusion

GridGreen makes pre-run carbon decisions visible. Future work: broader regions, VS Code extension, CI carbon budgets.

## References

To be completed for submission (CodeCarbon, Green Algorithms, Patterson et al., EIA API docs).
