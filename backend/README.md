# GridGreen — Backend

FastAPI service: **grid intelligence** (`estimate_carbon`, `check_grid`,
`find_clean_window`) plus **model suggestions** (`suggest_greener`, `scorecard`)
and optional **MCP** for Claude Desktop.

> API shapes: [`../CONTRACT.md`](../CONTRACT.md).

---

## Quick start

**Python:** **3.14** is supported. `requirements.txt` pins **pydantic 2.13.x**
so `pydantic-core` installs from **prebuilt cp314 wheels** (no local Rust build).

```bash
cd backend
python3.14 -m venv .venv && source .venv/bin/activate   # or python3.12, etc.
pip install -U pip setuptools wheel
pip install -r requirements.txt
cp .env.example .env
# Optional: EIA_API_KEY, SNOWFLAKE_*, GEMINI_API_KEY (see .env.example)
python -m scripts.ingest_eia   # works without EIA key (mock / synthetic data)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then:

- `http://localhost:8000/ping`
- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:8000/api/check_grid?region=CISO`
- `http://localhost:8000/api/find_clean_window?region=CISO&hours_needed=4`

## Tests

```bash
cd backend && source .venv/bin/activate
pytest -q
```

## MCP server (optional)

```bash
cd backend && source .venv/bin/activate
python -m app.mcp_server
```

Configure Claude Desktop using the frontend **`/mcp`** page (or your team’s JSON snippet).

---

## Layout

```
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── models/schemas.py
│   ├── routes/
│   └── services/
├── scripts/ingest_eia.py
├── tests/
├── data/                 # SQLite + cache (gitignored)
├── .env.example
└── requirements.txt
```

## Notes

- **Snowflake is optional in dev.** When `SNOWFLAKE_*` are unset, storage uses SQLite under `backend/data/`.
- **EIA is optional in dev.** Without `EIA_API_KEY`, ingest can still populate synthetic series for demos.
- **Heavy extras** (Prophet, sentence-transformers, Snowflake connector, W&B): `pip install -r requirements-extras.txt`.
