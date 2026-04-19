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
- `npm run lint` runs `next lint` with `eslint-config-next` pinned in
  `package.json`. If you ever see an interactive first-time ESLint prompt,
  run `npm run build` once — it also performs “lint + typecheck” as part of
  the Next build pipeline.

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

- **Backend (Render)**: see `render.yaml` + `backend/Procfile`
  - Set `CORS_ALLOW_ORIGINS` to your Vercel origin
  - Set `EIA_API_KEY` (recommended in prod)
  - Set `SQLITE_PATH` to a persistent path on the host (Render example path is documented in `render.yaml`)
- **Frontend (Vercel)**: set `BACKEND_URL` to the public Render API base URL

---

## What is implemented (functionality)

### Backend (Person A slice)

- **`GET /ping`**: health check
- **`GET /api/check_grid`**: current intensity + trend + `last_updated`
- **`GET /api/find_clean_window`**: optimal window + savings + **48h forecast series**
  - Prophet if installed; otherwise a deterministic seasonal-naive fallback
- **`POST /api/estimate_carbon`**: rules-based estimate + `detected_patterns`
- **`POST /api/suggest_greener`**: curated HF “greener alternative” suggestions via RAG (TF‑IDF baseline; upgrades if `sentence-transformers` is installed)
- **Optional context**
  - **`GET /api/context/weather`**: NOAA narrative layer (can 502 if upstream is flaky)
  - **`GET /api/context/campus_heat`**: Scripps-style heat map aggregate from bundled sample CSV

### Reliability / safety

- EIA client: chunking + retries + backoff + partial merge with mock series when needed
- Request size limits for code payloads
- Per-IP rate limiting + request timeout middleware
- Short TTL caching for forecast work (does not fake freshness timestamps)

### Still stub / other owner

- **`GET /api/scorecard`**: contract-valid stub (**Person B** owns the real aggregation)

### Frontend (Person A slice)

- Monaco editor + inline decorations + region selector
- “Run analysis” modal calling estimate + grid forecast endpoints and charting the 48h series
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
