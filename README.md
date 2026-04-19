# GridGreen

**Carbon-aware copilot for ML engineers.**

> Built at [DataHacks 2026](https://datahacks.ucsd.edu/) — Theme: Environment, Climate, & Energy Sciences | Tracks: AI/ML + Cloud

GridGreen analyzes ML training scripts, estimates their compute carbon footprint using published scaling laws, pairs that with real-time grid carbon intensity from the US EIA, and tells you **when** to run and **what smaller model** to consider — before a single GPU-hour is burned.

Available as a web app (Monaco editor + analysis UI) and as an MCP server for AI agents (Claude Desktop, Cursor, Claude Code).

> *"Every `model.fit()` is a climate decision. GridGreen makes that decision visible."*

---

## Features

- **Carbon estimation** — Paste any ML script; get estimated CO₂, GPU-hours, and kWh based on detected models, epochs, and batch size. Every response includes a `methodology` block with scaling-law citations and stated limitations.
- **Model-swap suggestions** — RAG-backed recommendations to swap large models for smaller, greener alternatives with cited benchmark retention (e.g. flan-t5-xxl → flan-t5-large: −85% compute, 94% MMLU retained). 58 curated model pairs covering LLMs, vision, audio, and classical ML.
- **Grid-aware scheduling** — 48-hour carbon intensity forecast from EIA data; find the cleanest window to run your workload.
- **Workload practice detection** — Identifies training patterns like AMP, FSDP, gradient checkpointing, `torch.compile`, quantization.
- **MCP server** — Full parity with the HTTP API, including Gemini-polished reasoning. Works with Claude Desktop, Cursor, and Claude Code.
- **Gemini NL reasoning** — Optional natural-language explanation of why a swap makes sense, powered by Gemini API.
- **Session scorecard** — Track cumulative CO₂ savings across suggestion acceptances and deferred runs.
- **Repo analyzer** — Analyze an entire GitHub repo's Python files for carbon-intensive patterns in one pass.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  FRONTEND — Next.js 15 / Tailwind / Monaco Editor   │
│  Code editor, inline hints, analysis modal, sidebar │
└────────────────────┬────────────────────────────────┘
                     │ HTTPS
┌────────────────────▼────────────────────────────────┐
│  BACKEND — FastAPI + MCP Server                     │
│                                                     │
│  /api/estimate_carbon    → Carbon Estimator (rules) │
│  /api/suggest_greener    → RAG Index + Gemini NL    │
│  /api/check_grid         → EIA Client + Forecaster  │
│  /api/find_clean_window  → Prophet / Seasonal-naive │
│  /api/scorecard          → Session Store            │
│  /api/diagnostics        → Health + EIA verification│
└──┬──────────┬───────────────────────────────────────┘
   │          │
┌──▼──────┐ ┌─▼────────────────────────┐
│ SQLite  │ │ Optional cloud backends  │
│ (local) │ │ Snowflake, Databricks,   │
│         │ │ Brev GPU, W&B, Gemini    │
└─────────┘ └──────────────────────────┘
```

---

## Quickstart

### Prerequisites

- Python 3.12+
- Node.js 20+

### Backend

```bash
# From repo root
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Optional: Prophet forecasting, SBERT embeddings, Snowflake
pip install -r backend/requirements-extras.txt

# Configure
cp backend/.env.example backend/.env
# Edit backend/.env — set EIA_API_KEY for real data (optional; mock works offline)

# Ingest EIA grid data
cd backend
python -m scripts.ingest_eia

# Run
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Paste an ML training script and click **Run Analysis**.

### Verify everything works

```bash
# Backend tests
cd backend && python -m pytest -q

# Frontend build + lint
cd frontend && npm run build && npm run lint

# Or use the all-in-one script
./scripts/verify_demo_readiness.sh
```

---

## API Reference

All endpoints are under `/api`. Full request/response schemas in [`CONTRACT.md`](CONTRACT.md).

| Endpoint | Method | Description |
|---|---|---|
| `/api/estimate_carbon` | POST | Estimate CO₂, GPU-hours, kWh from code + region |
| `/api/suggest_greener` | POST | RAG-backed model-swap suggestions with citations |
| `/api/check_grid` | GET | Current grid carbon intensity and trend |
| `/api/find_clean_window` | GET | Optimal low-carbon window in next 48h |
| `/api/scorecard` | GET | Session-level CO₂ savings tracker |
| `/api/diagnostics` | GET | Health check + EIA data verification |

### MCP Server

GridGreen exposes all five tools via MCP with full feature parity (including Gemini-polished reasoning when `GEMINI_API_KEY` is set):

```bash
cd backend
python mcp_server.py
```

To register with Claude Desktop, copy the config from the `/mcp` page in the frontend into `claude_desktop_config.json`, or add manually:

```json
{
  "mcpServers": {
    "gridgreen": {
      "command": "python",
      "args": ["/absolute/path/to/backend/mcp_server.py"],
      "env": {
        "SQLITE_PATH": "/absolute/path/to/backend/data/gridgreen.sqlite"
      }
    }
  }
}
```

---

## Evaluation

A self-evaluation harness in `evaluation/` runs 12 workloads across 4 scenarios. Latest results:

| Metric | Value |
|---|---|
| Success rate | **100%** (12/12 workloads) |
| Mean analysis latency | **<20ms** (in-process benchmark) |
| Suggestion coverage | **66.7%** of workloads receive ≥1 swap |
| Model-swap CO₂ reduction (LLMs) | **54.9%** |
| Model-swap CO₂ reduction (Vision/Audio) | **57.1%** |
| Model-swap CO₂ reduction (overall) | **37.0%** |
| Avg compute reduction per suggestion | **77.6%** |

Run the benchmark yourself:

```bash
GRIDGREEN_DISABLE_ST=1 GRIDGREEN_DISABLE_HF_HUB=1 \
  python -m evaluation.runner --config evaluation/configs/benchmark_config.json

python -m evaluation.metrics --run-dir evaluation/runs/<timestamp>
```

See [`evaluation/README.md`](evaluation/README.md) for details.

---

## Methodology and Limitations

GridGreen estimates are **rules-based and directional** — not metered datacenter power. The methodology is documented in every API response via the `methodology` field:

**How it works:**
1. **Model detection** — AST + regex to find `from_pretrained`, `create_model`, `model.fit`, training loops, etc.
2. **Parameter lookup** — Curated catalog of ~58 model pairs with parameter counts.
3. **FLOPs → energy scaling** — Based on published scaling laws:
   - [Patterson et al., 2022](https://arxiv.org/abs/2104.10350) — Carbon Emissions and Large Neural Network Training
   - [Kaplan et al., 2020](https://arxiv.org/abs/2001.08361) — Scaling Laws for Neural Language Models
   - [Strubell et al., 2019](https://arxiv.org/abs/1906.02243) — Energy and Policy Considerations for Deep Learning in NLP
4. **Grid intensity** — Real-time and forecast data from the US Energy Information Administration (EIA).

**What `carbon_saved_pct` actually means:**
The parameter-ratio compute reduction `(1 − params_to / params_from)` — a proxy for energy savings, not a metered delta. `performance_retained_pct` references published benchmark comparisons (MMLU, BIG-bench, Open LLM Leaderboard) where available.

**Known limitations:**
- No dataset-size awareness (static analysis only)
- Batch-size effect uses a heuristic
- Closed-API models (GPT-4, Claude) use a flat inference proxy
- No ground-truth validation against runtime telemetry yet

For metered energy, pair with [CodeCarbon](https://codecarbon.io/), RAPL, or DCGM.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS, Monaco Editor, Recharts, Framer Motion |
| Backend | Python, FastAPI, Pydantic |
| Data | EIA API, SQLite, Prophet / seasonal-naive forecasting |
| ML/RAG | Sentence-Transformers (MiniLM), TF-IDF fallback, curated HF corpus |
| AI | Gemini API (optional NL reasoning polish) |
| Cloud (optional) | Snowflake Cortex, Databricks DLT, AWS SageMaker, NVIDIA Brev, W&B |
| Agent | MCP server (Claude Desktop, Cursor, Claude Code) |

---

## Project Structure

```
green-watts/
├── backend/
│   ├── app/
│   │   ├── routes/          # FastAPI endpoints
│   │   ├── services/        # Core logic (estimator, forecaster, RAG, EIA)
│   │   ├── models/          # Pydantic schemas
│   │   └── data/            # hf_corpus.json (RAG pairs)
│   ├── scripts/             # Ingest, index-building, sponsor integrations
│   ├── tests/               # pytest suite (54 tests)
│   └── mcp_server.py        # MCP tool server
├── frontend/
│   └── src/
│       ├── app/             # Next.js pages
│       └── components/      # Monaco editor, modals, suggestion cards
├── evaluation/              # Self-evaluation harness + workloads
├── CONTRACT.md              # API contract (source of truth)
├── HOW_TO_RUN.md            # Detailed runbook
└── PLANNING.md              # Internal hackathon planning docs
```

---

## Other Docs

| File | Contents |
|---|---|
| [`CONTRACT.md`](CONTRACT.md) | API request/response schemas |
| [`HOW_TO_RUN.md`](HOW_TO_RUN.md) | Detailed setup, env vars, EIA verification |
| [`CLOUD_SETUP.md`](CLOUD_SETUP.md) | Step-by-step setup for each cloud integration |
| [`PLANNING.md`](PLANNING.md) | Internal hackathon planning (schedules, work splits, demo script) |
| [`evaluation/README.md`](evaluation/README.md) | Benchmark methodology and workload descriptions |

---

## Dataset

**EIA — US Energy Information Administration** (official DataHacks 2026 Non-Scripps Energy dataset). Hourly grid carbon intensity for 5 balancing authorities (CISO, ERCO, PJM, MISO, NYIS).

Verify data landed after ingest:

```bash
curl -s http://127.0.0.1:8000/api/diagnostics | python3 -m json.tool
# Check storage.eia_hourly.row_count, ts_min_utc, ts_max_utc
```

---

## Sponsor Integrations

GridGreen includes re-runnable scripts for each sponsor technology:

| Sponsor | Script | What it does |
|---|---|---|
| AWS | `python -m scripts.sagemaker_processing` | SageMaker Processing Job on `ml.t3.medium` |
| Snowflake | `python -m scripts.build_rag_index --target snowflake` | Cortex vector index with `VECTOR(FLOAT, 384)` |
| Databricks | `python -m scripts.dlt_pipeline` | Delta Live Tables EIA pipeline (local fallback included) |
| NVIDIA Brev | `python -m scripts.brev_embed` | GPU embedding workload + optional W&B logging |
| Google Gemini | Automatic when `GEMINI_API_KEY` is set | NL reasoning polish for suggestions |

All scripts run from `backend/`. See [`CLOUD_SETUP.md`](CLOUD_SETUP.md) for step-by-step setup of each service.

---

## License

Built at DataHacks 2026.
