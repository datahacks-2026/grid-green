"""Export local SQLite `eia_hourly` to CSV for Databricks UC / Volume upload.

Does not import `app.*` so it runs with only `pandas` (+ optional `python-dotenv`).

Run from `backend/` after ingesting data:

    python -m scripts.ingest_eia
    python -m scripts.export_eia_hourly_to_databricks_csv

Then upload the CSV to DBFS or a Unity Catalog Volume and use the optional
cell in `scripts/databricks/bronze_eia_raw_bootstrap.py`.
"""

from __future__ import annotations

import os
import sqlite3

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # notebook cell / exec — no __file__
    HERE = os.getcwd()
ROOT = os.path.dirname(HERE)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(os.path.join(ROOT, ".env"))
    load_dotenv(os.path.join(os.getcwd(), ".env"))


def _sqlite_path() -> str:
    """Resolve SQLITE_PATH like the app when you run from `backend/` (relative paths use cwd).

    Default `backend/data/gridgreen.sqlite` with cwd `backend/` → `backend/backend/data/...`
    (same as `sqlite3` + uvicorn from that directory). If not found, also tries paths under `ROOT`.
    """
    _load_dotenv()
    raw = (os.environ.get("SQLITE_PATH") or "backend/data/gridgreen.sqlite").strip().strip('"').strip("'")
    if os.path.isabs(raw):
        return raw
    for base in (os.getcwd(), ROOT):
        p = os.path.normpath(os.path.join(base, raw))
        if os.path.isfile(p):
            return p
    return os.path.normpath(os.path.join(os.getcwd(), raw))


def main() -> int:
    import pandas as pd

    db_path = _sqlite_path()
    if not os.path.isfile(db_path):
        print(f"SQLite file not found: {db_path}")
        print("Set SQLITE_PATH in backend/.env or run from repo with default backend/data/gridgreen.sqlite")
        return 1

    out_dir = os.path.join(ROOT, "data", "exports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "eia_hourly_export.csv")

    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql(
            "SELECT ts_utc, region_code, metric, value FROM eia_hourly ORDER BY region_code, ts_utc",
            conn,
        )
    finally:
        conn.close()

    if df.empty:
        print("No rows in eia_hourly — run: python -m scripts.ingest_eia")
        return 1

    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
