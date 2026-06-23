# GridGreen — Backend

FastAPI service: grid intelligence (`estimate_carbon`, `check_grid`,
`find_clean_window`), model suggestions (`suggest_greener`, `scorecard`),
repo analysis, and an optional MCP server for Claude Desktop / Cursor.

> API shapes: [`../CONTRACT.md`](../CONTRACT.md). Full setup: [`../HOW_TO_RUN.md`](../HOW_TO_RUN.md).

---

## Quick start

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
cp .env.example .env
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
python mcp_server.py
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
├── mcp_server.py
├── data/                 # SQLite + cache (gitignored)
├── .env.example
└── requirements.txt
```

## Notes

- **Snowflake is optional in dev.** When `SNOWFLAKE_*` are unset, storage uses SQLite under `backend/data/`.
- **EIA is optional in dev.** Without `EIA_API_KEY`, ingest can still populate synthetic series for demos.
- **Heavy extras** (Prophet, sentence-transformers, Snowflake connector, W&B): `pip install -r requirements-extras.txt`.
