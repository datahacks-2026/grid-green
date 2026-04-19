# GridGreen — how to run (local) + what is implemented

This file is the **practical runbook** for the repo. API shapes live in [`CONTRACT.md`](CONTRACT.md). Person A execution notes live in [`a.md`](a.md).

---

## Prerequisites

- **Python 3.12** (recommended; matches the project’s dependency set)
- **Node.js 20+** (recommended; Next.js 15 + the pinned ESLint toolchain emit
  `EBADENGINE` warnings on Node 18 in some installs)
- **Git**

Optional (for “full story” / prizes):

- **EIA API key** (`https://www.eia.gov/opendata/`)
- **Snowflake** credentials (optional; SQLite fallback works without them)
- **Databricks** workspace (optional; DLT is a separate pipeline story)
- **Claude Desktop** (optional; MCP integration)

---

## 1) Clone and enter the repo

```bash
git clone <your-repo-url>
cd green-watts
```

---

## 2) Backend (FastAPI)

### Create a virtualenv and install dependencies

From the **repository root**:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

Optional “heavier” dependencies (Prophet forecasting, semantic RAG embeddings, Snowflake client, W&B):

```bash
pip install -r backend/requirements-extras.txt
```

RAG embedding controls (optional):

- **`GRIDGREEN_DISABLE_ST=1`**: never try to download/load `sentence-transformers`
  models at runtime (forces TF‑IDF only — good for CI, locked-down networks,
  and fast cold starts).
- **`GRIDGREEN_ST_MODEL=...`**: override the MiniLM id when ST is enabled.
- **`GRIDGREEN_RAG_BACKEND=auto|snowflake|local`** (default `auto`):
  - `auto` — when `SNOWFLAKE_*` is configured **and** SBERT is loaded,
    rank candidates with Snowflake Cortex
    `VECTOR_COSINE_SIMILARITY(RAG_HF_CORPUS.embedding, query)`; otherwise
    fall back to local SBERT, then TF‑IDF.
  - `snowflake` — force Cortex (warns + falls back if it fails).
  - `local` — never call Snowflake, even if env is set.

  Run `python -m scripts.build_rag_index --target snowflake` once before
  enabling Cortex so `RAG_HF_CORPUS` is populated with `VECTOR(FLOAT, 384)`
  embeddings.

### Configure environment variables

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

- **`EIA_API_KEY`**: optional for local dev (without it, ingestion uses deterministic mock series). Set it for real EIA pulls.
- **`SQLITE_PATH`**: **set explicitly** to avoid path surprises depending on your working directory.

Recommended when you run uvicorn **from `backend/`** (see step below):

```env
SQLITE_PATH=data/gridgreen.sqlite
```

- **`CORS_ALLOW_ORIGINS`**: for local UI, keep:

```env
CORS_ALLOW_ORIGINS=http://localhost:3000
```

Snowflake is optional. If you fill `SNOWFLAKE_*`, the storage layer will try Snowflake and fall back to SQLite on failure.

### Seed local grid history (SQLite)

Run this **from `backend/`** so imports resolve consistently:

```bash
cd backend
source ../.venv/bin/activate
python -m scripts.ingest_eia --days 14
```

### Verify EIA data landed (dataset / judge check)

Still **from `backend/`**, after ingest:

```bash
sqlite3 data/gridgreen.sqlite "SELECT COUNT(*) AS rows, COUNT(DISTINCT region_code) AS regions, MIN(ts_utc), MAX(ts_utc) FROM eia_hourly;"
```

With the API running, open **`GET /api/diagnostics`** (e.g.
`http://127.0.0.1:8000/api/diagnostics`) and confirm
`storage.eia_hourly.table_found` is **true** and **`row_count` > 0**.

Or with `curl` + `jq` (copy-pasteable):

```bash
curl -s http://127.0.0.1:8000/api/diagnostics | jq '.storage.eia_hourly'
```

Expected output after a successful ingest:

```json
{
  "table_found": true,
  "row_count": 3600,
  "distinct_regions": 5,
  "ts_min_utc": "2026-04-05T00:00:00+00:00",
  "ts_max_utc": "2026-04-19T00:00:00+00:00",
  "note": null
}
```

From the **repository root**, you can run an automated pre-flight before
recording a demo or opening a PR:

```bash
./scripts/verify_demo_readiness.sh
```

### Start the API

Still **from `backend/`**:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If you run `uvicorn` **from the repo root** instead, Python will not find the `app`
package (`ModuleNotFoundError: No module named 'app'`). Either `cd backend` first,
or from the **repository root** (venv activated):

```bash
chmod +x scripts/run-backend.sh   # once
./scripts/run-backend.sh
```

(`PORT=8001 ./scripts/run-backend.sh` overrides the port.)

Sanity URLs:

- `http://127.0.0.1:8000/ping`
- `http://127.0.0.1:8000/docs`

### Backend tests

```bash
cd backend
source ../.venv/bin/activate
pytest -q
```

The suite is small but exercises HTTP routes, optional context endpoints,
MCP tool registration, and the local DLT fallback runner.

---

## 3) Frontend (Next.js)

### Install and configure

```bash
cd frontend
npm install
cp .env.example .env.local
```

Edit `frontend/.env.local`:

- **`BACKEND_URL`**: should point at your running API, typically:

```env
BACKEND_URL=http://127.0.0.1:8000
```

### Run the dev server

```bash
npm run dev
```

Open `http://localhost:3000`.

Notes:

- `npm run typecheck` should pass.
- `npm run build` should pass.
- `npm run lint` runs ESLint CLI (`eslint . --max-warnings=0`) with a committed
  `.eslintrc.json`, so it is non-interactive and CI-safe.

Layout note: the App Router lives under **`frontend/src/app/`** (not
`frontend/app/`).

---

## 4) MCP (Claude Desktop) — optional

The MCP server entrypoint is:

- `backend/mcp_server.py`

Run manually (stdio):

```bash
cd backend
source ../.venv/bin/activate
python mcp_server.py
```

Claude Desktop configuration is environment-specific; use the docstring at the top of `mcp_server.py` as the copy/paste template.

---

## 5) Optional scripts (prizes / demos)

### Databricks DLT + local fallback

- File: `backend/scripts/dlt_pipeline.py`
- Local fallback:

```bash
cd backend
source ../.venv/bin/activate
python -m scripts.dlt_pipeline
```

### Brev / embeddings workload (+ optional W&B)

```bash
cd backend
source ../.venv/bin/activate
pip install -r ../backend/requirements-extras.txt   # if not already
python -m scripts.brev_embed
```

### AWS SageMaker Processing (optional — sponsor / credits story)

This launches a tiny **SageMaker ProcessingJob** that reads the bundled HF corpus
JSON from S3, prints a summary, and writes `summary.json` back to S3. It is
**not** wired into the FastAPI runtime.

Prereqs:

- AWS credentials with `sagemaker:CreateProcessingJob` + S3 read/write + IAM PassRole
- Fill `SAGEMAKER_*` vars in `backend/.env` (see `.env.example`)

```bash
cd backend
source ../.venv/bin/activate
pip install -r ../backend/requirements-extras.txt
python -m scripts.sagemaker_processing --wait
```

### Snowflake Cortex upload (optional)

Requires Snowflake configured in `backend/.env` and extras installed:

```bash
cd backend
source ../.venv/bin/activate
python -m scripts.build_rag_index --target snowflake
```

---

## 6) Deploy (public URLs) — high level

- **Backend (Render)**: see `render.yaml` (Blueprint — start command,
  health check, and env vars are all declared there; no separate
  `Procfile` is needed)
  - Set `CORS_ALLOW_ORIGINS` to your Vercel origin
  - Set `EIA_API_KEY` (recommended in prod)
  - Set `SQLITE_PATH` to a persistent path on the host (Render example path is documented in `render.yaml`)
- **Frontend (Vercel)**: import the `frontend/` directory in Vercel
  (Next.js is auto-detected — no `vercel.json` needed). **`.env.local`
  is gitignored and is NOT deployed by Vercel** — set the same vars in
  Vercel project settings → Environment Variables for **Production +
  Preview**:
  - `BACKEND_URL` → public Render API base URL (used by server
    components / API routes proxying the backend)
  - `NEXT_PUBLIC_API_BASE_URL` → same URL (exposed to the browser)
  See `frontend/.env.example` and `frontend/.env.local.example` for the
  shape of the values.

---

## What is implemented (functionality)

### Backend (Person A slice)

- **`GET /ping`**: health check
- **`GET /api/diagnostics`**: shows which integrations are configured / importable
  (Snowflake, Databricks, Gemini, EIA, NOAA, Hugging Face, GitHub repo fetcher),
  plus SQLite path + RAG corpus size. Cheap — does *not* open external connections.
- **`GET /api/check_grid`**: current intensity + trend + `last_updated`
- **`GET /api/find_clean_window`**: optimal window + savings + **48h forecast series**
  - Prophet if installed; otherwise a deterministic seasonal-naive fallback
- **`POST /api/estimate_carbon`**: rules-based estimate + `detected_patterns`
- **`POST /api/suggest_greener`**: curated “greener alternative” suggestions via RAG.
  Detects model loads from `from_pretrained(...)`, `pipeline(model=...)`,
  `LLM(model=...)`, `ChatOpenAI(model=...)`, `client.chat.completions.create(model=...)`,
  bare HF org/model literals (`meta-llama/...`, `mistralai/...`, etc.), API-only
  ids (`gpt-4-turbo`, `claude-3-opus-...`, `gemini-1.5-pro`, ...), and top-level
  assignments like `MODEL_ID = "..."`. TF-IDF baseline; upgrades if
  `sentence-transformers` is installed.
- **`POST /api/analyze_repo`**: scan a public GitHub repo for greener-model swaps.
  Body: `{ "repo_url": "https://github.com/owner/repo", "ref"?, "region"? }`.
  Response also includes **`aggregated_code_for_estimate`** (joined `.py` / notebook
  cells, byte-capped like pasted code) so the UI can call **`POST /api/estimate_carbon`**
  and **`GET /api/find_clean_window`** for the same “when to run” / forecast flow as code mode.
  Set `GITHUB_TOKEN` to raise the API rate limit / scan private repos.
- **Optional context**
  - **`GET /api/context/weather`**: NOAA narrative layer (can 502 if upstream is flaky)
  - **`GET /api/context/campus_heat`**: Scripps-style heat map aggregate from bundled sample CSV

### Reliability / safety

- EIA client: chunking + retries + backoff + partial merge with mock series when needed
- Request size limits for code payloads
- Per-IP rate limiting + request timeout middleware
- Short TTL caching for forecast work (does not fake freshness timestamps)

### Scorecard

- **`GET /api/scorecard`** + **`POST /api/scorecard/event`**: real in-memory
  aggregation backed by `app/services/session_scorecard.py`. Mirrored as the
  `get_scorecard` MCP tool in `backend/mcp_server.py`.

### Frontend (Person A slice)

- **Code / Repo URL** input toggle in the header
  - **Code mode**: Monaco editor + inline decorations + live suggestion sidebar (no
    "Run analysis" required to see swaps; clicking it enriches each suggestion with
    grid + script CO₂ context).
  - **Repo URL mode**: paste a public GitHub URL → the backend downloads the
    zipball, runs greener-model detection across `.py` / `.ipynb` files, and
    renders per-file suggestions.
- Region selector
- "Run analysis" modal calling estimate + grid forecast endpoints and
  charting the 48h series. The modal also fires three best-effort
  enrichment calls in parallel (`/api/suggest_greener`,
  `/api/context/weather`, `/api/context/campus_heat`) and renders, when
  available, a NOAA / Scripps context strip plus the top RAG suggestion
  with its Gemini-polished reasoning paragraph below the chart. Any of
  the three may fail (NOAA 502, empty corpus, missing Scripps CSV)
  without blocking the chart.
- **`/mcp` page** (`frontend/src/app/mcp/page.tsx`): copy/paste helper for Claude Desktop wiring

### Tooling / integration files

- **`backend/mcp_server.py`**: MCP tools mirroring the HTTP service layer
- **`backend/scripts/dlt_pipeline.py`**: Databricks DLT definition + local fallback runner
- **`backend/scripts/brev_embed.py`**: GPU embedding workload + optional W&B logging
- **`render.yaml`**: Render blueprint skeleton

---

## Common pitfalls

- **Run uvicorn from `backend/`** (recommended) so module paths and SQLite paths behave predictably.
- If SQLite ends up under an unexpected nested folder, fix it by setting **`SQLITE_PATH`** explicitly (recommended: `data/gridgreen.sqlite` when cwd is `backend/`).
- NOAA and EIA are **external services**: failures should be treated as upstream flakiness, not necessarily app bugs.

---

## Verifying integrations

Quickest end-to-end check (with the API running on `:8000`):

```bash
# 1. Liveness + which integrations the process can see.
curl -s http://127.0.0.1:8000/api/diagnostics | python -m json.tool

# 2. Suggestions for HF, OpenAI, and assignment-style model ids.
curl -s -X POST http://127.0.0.1:8000/api/suggest_greener \
  -H 'content-type: application/json' \
  -d '{"code":"MODEL_ID = \"google/flan-t5-xxl\"\nfrom openai import OpenAI\nOpenAI().chat.completions.create(model=\"gpt-4-turbo\", messages=[])\n"}' \
  | python -m json.tool

# 3. Repo-mode scan against a small public repo.
curl -s -X POST http://127.0.0.1:8000/api/analyze_repo \
  -H 'content-type: application/json' \
  -d '{"repo_url":"https://github.com/huggingface/transformers","ref":"main"}' \
  | python -m json.tool | head -40
```

Live external handshakes (Snowflake / Databricks SQL warehouses) are intentionally
*not* part of `/api/diagnostics` because they can hang. Use the dedicated smoke
scripts when you need them:

```bash
cd backend && source ../.venv/bin/activate
python -m scripts.databricks_sql_smoke   # Databricks SQL warehouse
python -m scripts.build_rag_index --target snowflake   # Snowflake Cortex (extras only)
```
