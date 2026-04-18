# GridGreen — Backend (Person A)

FastAPI service for the **Grid intelligence** slice. Ships three real
endpoints (`estimate_carbon`, `check_grid`, `find_clean_window`) and
contract-valid stubs for Person B's two endpoints (`suggest_greener`,
`scorecard`) so the frontend / MCP / Claude wiring can be built end-to-end
before Phase 5.

> Source of truth for shapes: [`../CONTRACT.md`](../CONTRACT.md).

---

## Quick start

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # fill in EIA / Snowflake keys when you have them
python -m scripts.ingest_eia     # works without keys (mock data)
uvicorn app.main:app --reload --port 8000
```

Then:

- `http://localhost:8000/ping`
- `http://localhost:8000/docs` (Swagger UI)
- `http://localhost:8000/api/check_grid?region=CISO`
- `http://localhost:8000/api/find_clean_window?region=CISO&hours_needed=4`

## Tests

```bash
cd backend
pytest -q
```

## Layout

```
backend/
├── app/
│   ├── main.py                 # FastAPI factory + CORS + routers
│   ├── config.py               # env loading (pydantic-settings)
│   ├── models/schemas.py       # Pydantic shapes mirroring CONTRACT.md
│   ├── routes/
│   │   ├── health.py           # /ping, /
│   │   ├── grid.py             # Person A — 3 endpoints
│   │   └── stubs.py            # Person B — contract-valid placeholders
│   └── services/
│       ├── regions.py          # supported balancing authorities
│       ├── eia_client.py       # EIA fetch + offline mock generator
│       ├── storage.py          # Snowflake (when configured) → SQLite fallback
│       ├── forecaster.py       # 48h seasonal-naive baseline (Prophet later)
│       └── carbon_estimator.py # rules-based code → gCO2
├── scripts/
│   └── ingest_eia.py           # one-shot ingest (use cron or manual refresh)
├── tests/
│   └── test_smoke.py
├── data/                       # SQLite + cache live here (gitignored)
├── .env.example
└── requirements.txt
```

## Notes

- **Snowflake is optional in dev.** When `SNOWFLAKE_*` are unset the storage
  layer transparently uses SQLite at `backend/data/gridgreen.sqlite`.
- **EIA is optional in dev.** When `EIA_API_KEY` is unset the ingest script
  writes a deterministic synthetic series so the demo path works offline.
- **Prophet** is in `requirements.txt` for Phase 3 — the current forecaster
  uses a seasonal-naive baseline so the API is real-shaped from day one.
- Phase 5 swaps the small built-in model catalog in `carbon_estimator.py`
  for a Snowflake Cortex / RAG lookup over Hugging Face model cards.
