# GridGreen

Carbon-aware analysis for ML training workloads.

GridGreen estimates the carbon footprint of a training script before you run it. It parses your code to detect models and training settings, combines that with grid carbon intensity data, and returns CO₂ estimates, greener model alternatives, and a low-carbon scheduling window.

Built at [DataHacks 2026](https://datahacks.ds3ucsd.com/) (Environment, Climate & Energy). Winner of the Cloud Track and MLH Best Use of Snowflake API. [Devpost](https://devpost.com/software/greenwatts) · [Demo video](https://youtu.be/RwTjxSpgrts)

## Features

- **Carbon estimation.** Static analysis of training scripts to estimate CO₂, GPU-hours, and kWh. Results include a documented methodology and stated limitations.
- **Model recommendations.** Retrieval over a curated catalog of model pairs, with benchmark citations and optional Gemini reasoning.
- **Grid scheduling.** Hourly carbon intensity from the US EIA, with a 48-hour forecast to find a cleaner run window.
- **Workload detection.** Flags common efficiency practices (AMP, FSDP, gradient checkpointing, `torch.compile`, quantization).
- **Repository analysis.** Scans a GitHub repository for carbon-intensive patterns across Python files.
- **Session scorecard.** Tracks cumulative CO₂ savings from accepted suggestions and deferred runs.
- **MCP server.** Exposes the same capabilities to Claude Desktop, Cursor, and Claude Code.

## Quick start

**Requirements:** Python 3.12+, Node.js 20+

### Backend

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cp backend/.env.example backend/.env
# Optional: set EIA_API_KEY for live grid data (synthetic data works offline)

cd backend
python -m scripts.ingest_eia
uvicorn app.main:app --reload --port 8000
```

Optional dependencies (Prophet, Sentence-Transformers, Snowflake):

```bash
pip install -r backend/requirements-extras.txt
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Tests

```bash
cd backend && python -m pytest -q
cd frontend && npm run build && npm run lint
```

Or run `./scripts/verify_demo_readiness.sh` from the repository root.

## API

Request and response schemas are defined in [`CONTRACT.md`](CONTRACT.md).

| Endpoint | Method | Description |
|---|---|---|
| `/api/estimate_carbon` | POST | Estimate CO₂, GPU-hours, and kWh from code and region |
| `/api/suggest_greener` | POST | Model-swap suggestions with citations |
| `/api/check_grid` | GET | Current grid carbon intensity |
| `/api/find_clean_window` | GET | Lowest-carbon window in the next 48 hours |
| `/api/scorecard` | GET | Session CO₂ savings |
| `/api/diagnostics` | GET | Health check and EIA data status |

### MCP

```bash
cd backend
python mcp_server.py
```

Example `claude_desktop_config.json` entry:

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

The frontend `/mcp` page also provides a copy-ready configuration.

## Architecture

```
Frontend (Next.js, Monaco, Tailwind)
        |
        |  /api/*
        v
Backend (FastAPI)
  - Carbon estimator (AST + regex)
  - RAG suggestions (curated model corpus)
  - Grid forecaster (EIA + Prophet / seasonal-naive)
  - Session scorecard
        |
        +-- SQLite (local)
        +-- Snowflake, Databricks, SageMaker, Brev (optional)
```

## Methodology

Estimates are rules-based, not metered power readings. The pipeline:

1. Detects models and training parameters via AST and regex.
2. Looks up parameter counts in a curated catalog (~60 model pairs).
3. Converts compute to energy using published scaling laws ([Patterson et al., 2022](https://arxiv.org/abs/2104.10350); [Kaplan et al., 2020](https://arxiv.org/abs/2001.08361); [Strubell et al., 2019](https://arxiv.org/abs/1906.02243)).
4. Applies grid carbon intensity from the US EIA (CISO, ERCO, PJM, MISO, NYIS).

Limitations: no dataset-size awareness, heuristic batch-size scaling, flat proxy for closed API models, no runtime telemetry validation by default. For measured energy use, pair with [CodeCarbon](https://codecarbon.io/), RAPL, or DCGM.

## Evaluation

The harness in `evaluation/` runs 12 workloads across four scenarios.

| Metric | Result |
|---|---|
| Success rate | 100% (12/12) |
| Mean analysis latency | <20 ms |
| Suggestion coverage | 66.7% |
| Mean compute reduction per suggestion | 77.6% |

```bash
GRIDGREEN_DISABLE_ST=1 GRIDGREEN_DISABLE_HF_HUB=1 \
  python -m evaluation.runner --config evaluation/configs/benchmark_config.json

python -m evaluation.metrics --run-dir evaluation/runs/<timestamp>
```

See [`evaluation/README.md`](evaluation/README.md) for details.

## Cloud integrations

Scripts run from `backend/`. Setup instructions are in [`HOW_TO_RUN.md`](HOW_TO_RUN.md).

| Service | Command |
|---|---|
| AWS SageMaker | `python -m scripts.sagemaker_processing` |
| Snowflake Cortex | `python -m scripts.build_rag_index --target snowflake` |
| Databricks DLT | `python -m scripts.dlt_pipeline` |
| NVIDIA Brev | `python -m scripts.brev_embed` |
| Google Gemini | Set `GEMINI_API_KEY` in `.env` |

## Data

Hourly grid carbon intensity from the [US EIA](https://www.eia.gov/opendata/), covering five balancing authorities: CISO, ERCO, PJM, MISO, and NYIS.

After ingest, verify storage:

```bash
curl -s http://127.0.0.1:8000/api/diagnostics | python3 -m json.tool
```

## Project structure

```
grid-green/
├── backend/
│   ├── app/              # FastAPI routes and services
│   ├── scripts/          # Ingest, RAG index, cloud integrations
│   ├── tests/
│   └── mcp_server.py
├── frontend/
│   └── src/              # Next.js app and components
├── evaluation/           # Benchmark harness
├── CONTRACT.md           # API schemas
└── HOW_TO_RUN.md         # Setup and integration guide
```

## Documentation

| File | Description |
|---|---|
| [`CONTRACT.md`](CONTRACT.md) | API request and response schemas |
| [`HOW_TO_RUN.md`](HOW_TO_RUN.md) | Environment setup, EIA ingest, cloud integrations |
| [`evaluation/README.md`](evaluation/README.md) | Benchmark and CodeCarbon validation |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Render, Vercel, and remote MCP (SSE) |
| [`docs/paper/DRAFT.md`](docs/paper/DRAFT.md) | Workshop paper draft |
| [`docs/paper/RELATED_WORK.md`](docs/paper/RELATED_WORK.md) | Related work notes |

## License

See [LICENSE](LICENSE).
