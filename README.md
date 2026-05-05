# GridGreen

[![Cloud Track Winner](https://img.shields.io/badge/DataHacks_2026-Cloud_Track_Winner-FFD700?style=flat-square)]()
[![MLH Best Use of Snowflake](https://img.shields.io/badge/MLH-Best_Use_of_Snowflake-4A90D9?style=flat-square)]()
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue?style=flat-square)](https://www.python.org/)
[![Node 20+](https://img.shields.io/badge/node-20+-brightgreen?style=flat-square)](https://nodejs.org/)

**Carbon-aware copilot for ML engineers.**

> Built at [DataHacks 2026](https://datahacks.ds3ucsd.com/) · [Devpost](https://devpost.com/software/greenwatts) · Theme: Environment, Climate & Energy Sciences · Tracks: AI/ML + Cloud

ML training is one of the fastest-growing sources of compute emissions in the tech industry, and most engineers have no visibility into a job's carbon cost before they run it. GridGreen fills that gap: paste a training script, get CO2, GPU-hours, and kWh estimates before a single GPU-hour is burned, along with a greener model alternative and the lowest-carbon time window to run it.

Available as a web app with a Monaco code editor and as an MCP server that works with Claude Desktop, Cursor, and Claude Code.

> *"Every `model.fit()` is a climate decision. GridGreen makes that decision visible."*

---

## Demo

[![GridGreen Demo](https://img.youtube.com/vi/RwTjxSpgrts/maxresdefault.jpg)](https://youtu.be/RwTjxSpgrts)

> **Status:** Local development -- clone and run locally. MCP server works with Claude Desktop and Cursor out of the box. Cloud deployment planned after evaluation and model generalization.

---

## What It Does

| Capability | How |
|---|---|
| **Carbon estimation** | AST + regex parses a submitted script to detect model names, epochs, and batch size. FLOPs are computed using published scaling laws and converted to kWh and CO2 using real-time grid intensity. |
| **Model-swap suggestions** | RAG system over 58 curated model pairs (Sentence-Transformers MiniLM + TF-IDF fallback) recommends smaller alternatives with cited benchmark retention. Example: `flan-t5-xxl` to `flan-t5-large` gives -85% compute with 94% MMLU retained. |
| **Grid-aware scheduling** | 48-hour carbon intensity forecast from EIA data using Prophet or seasonal-naive forecasting. Surfaces the lowest-carbon window to run your workload. |
| **Workload practice detection** | Identifies AMP, FSDP, gradient checkpointing, `torch.compile`, and quantization patterns in submitted code. |
| **MCP server** | Full HTTP API parity as an MCP tool server. Plug into Claude Desktop, Cursor, or Claude Code with a single config entry. |
| **Repo analyzer** | Scans an entire GitHub repo's Python files for carbon-intensive patterns in one pass. |
| **Session scorecard** | Tracks cumulative CO2 savings across accepted suggestions and deferred runs. |

---

## Evaluation Results

Self-evaluation harness in `evaluation/` runs 12 workloads across 4 scenarios.

| Metric | Result |
|---|---|
| Success rate | **100%** (12/12 workloads) |
| Mean analysis latency | **<20ms** (in-process) |
| Suggestion coverage | **66.7%** of workloads receive at least 1 swap |
| CO2 reduction (LLMs) | **54.9%** |
| CO2 reduction (Vision/Audio) | **57.1%** |
| CO2 reduction (overall) | **37.0%** |
| Avg compute reduction per suggestion | **77.6%** |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS, Monaco Editor, Recharts, Framer Motion |
| Backend | Python 3.12, FastAPI, Pydantic |
| Data | EIA API, SQLite, Prophet / seasonal-naive forecasting |
| ML / RAG | Sentence-Transformers (MiniLM), TF-IDF fallback, curated HF corpus (58 model pairs) |
| AI | Gemini API (optional natural-language reasoning) |
| Cloud | Snowflake Cortex, Databricks DLT, AWS SageMaker, NVIDIA Brev, W&B |
| Agent | MCP server -- Claude Desktop, Cursor, Claude Code |

---

## Architecture

```
+-----------------------------------------------------+
|  FRONTEND -- Next.js 15 / Tailwind / Monaco Editor  |
|  Code editor, inline hints, analysis modal, sidebar |
+--------------------+--------------------------------+
                     | HTTPS
+--------------------v--------------------------------+
|  BACKEND -- FastAPI + MCP Server                    |
|                                                     |
|  /api/estimate_carbon    -> Carbon Estimator (AST)  |
|  /api/suggest_greener    -> RAG Index + Gemini NL   |
|  /api/check_grid         -> EIA Client + Forecaster |
|  /api/find_clean_window  -> Prophet/Seasonal-naive  |
|  /api/scorecard          -> Session Store           |
|  /api/diagnostics        -> Health + EIA check      |
+--+----------+-------------------------------------------+
   |          |
+--v------+ +-v----------------------------+
| SQLite  | | Cloud backends               |
| (local) | | Snowflake, Databricks,       |
|         | | Brev GPU, W&B, Gemini        |
+---------+ +------------------------------+
```

---

## Methodology and Limitations

GridGreen estimates are rules-based and directional, not metered datacenter power. Every API response includes a `methodology` field documenting how the estimate was produced.

**Pipeline:**

1. **Model detection.** AST and regex scan for `from_pretrained`, `create_model`, `model.fit`, and training loop patterns.
2. **Parameter lookup.** Detected models are matched against a curated catalog of ~58 model pairs with parameter counts. Models outside the catalog receive a fallback heuristic estimate.
3. **FLOPs to energy.** Scaling laws from Patterson et al. (2022), Kaplan et al. (2020), and Strubell et al. (2019) convert parameter counts and epoch estimates to FLOPs, then to kWh.
4. **Grid intensity.** Real-time and forecast data from the US EIA for 5 balancing authorities (CISO, ERCO, PJM, MISO, NYIS).

**Known limitations:**

- Static analysis only -- no dataset-size awareness
- Batch-size scaling uses a heuristic
- Closed-API models (GPT-4, Claude) use a flat inference proxy
- No ground-truth validation against runtime telemetry yet

For metered energy, pair GridGreen with [CodeCarbon](https://codecarbon.io/), RAPL, or DCGM.

---

## Prerequisites

- Python 3.12+
- Node.js 20+
- EIA API key (free at [eia.gov](https://www.eia.gov/opendata/)) -- optional, mock works offline

---

## Quickstart

### 1. Backend

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Optional: Prophet forecasting, SBERT embeddings, Snowflake
pip install -r backend/requirements-extras.txt

cp backend/.env.example backend/.env
# Set EIA_API_KEY in backend/.env for real grid data (mock works without it)

cd backend
python -m scripts.ingest_eia
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000), paste an ML training script, and click **Run Analysis**.

### 3. Verify

```bash
cd backend && python -m pytest -q
cd frontend && npm run build && npm run lint

# Or run everything at once
./scripts/verify_demo_readiness.sh
```

---

## API Reference

Full request/response schemas in [`CONTRACT.md`](CONTRACT.md).

| Endpoint | Method | Description |
|---|---|---|
| `/api/estimate_carbon` | POST | CO2, GPU-hours, kWh from code and region |
| `/api/suggest_greener` | POST | RAG-backed model-swap suggestions with citations |
| `/api/check_grid` | GET | Current grid carbon intensity and trend |
| `/api/find_clean_window` | GET | Lowest-carbon window in the next 48 hours |
| `/api/scorecard` | GET | Session-level CO2 savings |
| `/api/diagnostics` | GET | Health check and EIA data verification |

### MCP Server

```bash
cd backend
python mcp_server.py
```

Add to `claude_desktop_config.json`:

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

## Cloud Integrations

All scripts run from `backend/`. See [`CLOUD_SETUP.md`](CLOUD_SETUP.md) for step-by-step setup.

| Integration | Script | What it does |
|---|---|---|
| AWS | `python -m scripts.sagemaker_processing` | SageMaker Processing Job on `ml.t3.medium` |
| Snowflake | `python -m scripts.build_rag_index --target snowflake` | Cortex vector index with `VECTOR(FLOAT, 384)` |
| Databricks | `python -m scripts.dlt_pipeline` | Delta Live Tables EIA pipeline (local fallback included) |
| NVIDIA Brev | `python -m scripts.brev_embed` | GPU embedding workload with optional W&B logging |
| Google Gemini | Automatic when `GEMINI_API_KEY` is set | Natural-language reasoning for swap suggestions |

---

## Dataset

Hourly grid carbon intensity from the US Energy Information Administration (EIA), the official DataHacks 2026 Non-Scripps Energy dataset. Covers 5 balancing authorities: CISO, ERCO, PJM, MISO, and NYIS.

Verify data after ingest:

```bash
curl -s http://127.0.0.1:8000/api/diagnostics | python3 -m json.tool
# Check storage.eia_hourly.row_count, ts_min_utc, ts_max_utc
```

---

## Run the Evaluation

```bash
GRIDGREEN_DISABLE_ST=1 GRIDGREEN_DISABLE_HF_HUB=1 \
  python -m evaluation.runner --config evaluation/configs/benchmark_config.json

python -m evaluation.metrics --run-dir evaluation/runs/<timestamp>
```

See [`evaluation/README.md`](evaluation/README.md) for workload descriptions and methodology.

---

## Project Structure

```
grid-green/
+-- backend/
|   +-- app/
|   |   +-- routes/          # FastAPI endpoints
|   |   +-- services/        # Core logic (estimator, forecaster, RAG, EIA)
|   |   +-- models/          # Pydantic schemas
|   |   +-- data/            # hf_corpus.json (RAG pairs)
|   +-- scripts/             # Ingest, index-building, cloud integrations
|   +-- tests/               # pytest suite (56 tests)
|   +-- mcp_server.py        # MCP tool server
+-- frontend/
|   +-- src/
|       +-- app/             # Next.js pages
|       +-- components/      # Monaco editor, modals, suggestion cards
+-- evaluation/              # Self-evaluation harness and workloads
+-- CONTRACT.md              # API contract (source of truth)
+-- HOW_TO_RUN.md            # Detailed runbook
+-- CLOUD_SETUP.md           # Cloud integration setup
+-- PLANNING.md              # Hackathon planning docs
```

---

## Other Docs

| File | Contents |
|---|---|
| [`CONTRACT.md`](CONTRACT.md) | API request/response schemas |
| [`HOW_TO_RUN.md`](HOW_TO_RUN.md) | Detailed setup, env vars, EIA verification |
| [`CLOUD_SETUP.md`](CLOUD_SETUP.md) | Step-by-step setup for each cloud integration |
| [`evaluation/README.md`](evaluation/README.md) | Benchmark methodology and workload descriptions |

---

## Roadmap

**Evaluation and reliability**
- [ ] Ground-truth validation against runtime telemetry (CodeCarbon, DCGM, RAPL)
- [ ] Dataset-size aware carbon estimation
- [ ] Expand model catalog beyond 58 pairs
- [ ] Multi-region grid support beyond 5 EIA balancing authorities

**Deployment**
- [ ] Cloud deployment (FastAPI on Railway, Next.js on Vercel)
- [ ] Remote MCP server (currently local-only)

**Integrations**
- [ ] VS Code extension
- [ ] CI/CD carbon budget checks in GitHub Actions
- [ ] Closed-API model support (GPT-4, Claude) beyond flat inference proxy

---

## License

Built at DataHacks 2026
