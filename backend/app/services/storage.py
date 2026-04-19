"""Storage facade with Snowflake → SQLite fallback.

Person A note: README §10 contingency — if Snowflake auth fails, fall back to
local SQLite so the demo path keeps working. This module hides the choice
behind a single read API.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from app.config import get_settings

logger = logging.getLogger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS eia_hourly (
    ts_utc      TEXT    NOT NULL,
    region_code TEXT    NOT NULL,
    metric      TEXT    NOT NULL,
    value       REAL    NOT NULL,
    ingested_at TEXT    NOT NULL,
    PRIMARY KEY (ts_utc, region_code, metric)
);
CREATE INDEX IF NOT EXISTS idx_eia_hourly_region_ts
    ON eia_hourly (region_code, ts_utc);
"""


def _ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def sqlite_conn() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    _ensure_dir(settings.sqlite_path)
    conn = sqlite3.connect(settings.sqlite_path)
    try:
        for stmt in SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        yield conn
    finally:
        conn.close()


def insert_eia_rows(rows: Sequence[Tuple[str, str, str, float]]) -> int:
    """rows: (ts_utc_iso, region_code, metric, value).

    Returns number of rows attempted. Uses Snowflake if configured,
    otherwise SQLite. Snowflake path is a thin best-effort; failures
    fall back to SQLite so ingestion never silently drops data.
    """
    if not rows:
        return 0

    settings = get_settings()
    now = datetime.now(timezone.utc).isoformat()
    payload = [(ts, region, metric, float(value), now) for ts, region, metric, value in rows]

    if settings.use_snowflake:
        try:
            return _insert_snowflake(payload)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            msg = str(exc)
            hint = ""
            if "42501" in msg or "Insufficient privileges" in msg:
                fq = f"{settings.snowflake_database}.{settings.snowflake_schema}.EIA_HOURLY"
                role = settings.snowflake_role or "YOUR_ROLE"
                sch = f"{settings.snowflake_database}.{settings.snowflake_schema}"
                hint = (
                    f" Snowflake: MERGE needs INSERT+UPDATE on {fq}. "
                    f"As owner/admin: GRANT INSERT, UPDATE ON TABLE {fq} TO ROLE {role}; "
                    f"if the table is missing: GRANT CREATE TABLE ON SCHEMA {sch} TO ROLE {role};"
                )
            logger.warning("Snowflake insert failed (%s); falling back to SQLite.%s", exc, hint)

    return _insert_sqlite(payload)


def _insert_sqlite(payload: List[Tuple[str, str, str, float, str]]) -> int:
    with sqlite_conn() as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO eia_hourly
                (ts_utc, region_code, metric, value, ingested_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            payload,
        )
        conn.commit()
    return len(payload)


def _insert_snowflake(payload: List[Tuple[str, str, str, float, str]]) -> int:
    import snowflake.connector  # type: ignore

    settings = get_settings()
    ctx = snowflake.connector.connect(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
        password=settings.snowflake_password,
        warehouse=settings.snowflake_warehouse,
        database=settings.snowflake_database,
        schema=settings.snowflake_schema,
        role=settings.snowflake_role,
    )
    try:
        cs = ctx.cursor()
        cs.execute(
            """
            CREATE TABLE IF NOT EXISTS eia_hourly (
                ts_utc      TIMESTAMP_NTZ,
                region_code STRING,
                metric      STRING,
                value       FLOAT,
                ingested_at TIMESTAMP_NTZ
            )
            """
        )
        cs.executemany(
            """
            MERGE INTO eia_hourly t
            USING (SELECT %s AS ts_utc, %s AS region_code, %s AS metric,
                          %s AS value, %s AS ingested_at) s
            ON t.ts_utc = s.ts_utc
               AND t.region_code = s.region_code
               AND t.metric = s.metric
            WHEN MATCHED THEN UPDATE SET value = s.value, ingested_at = s.ingested_at
            WHEN NOT MATCHED THEN INSERT (ts_utc, region_code, metric, value, ingested_at)
                VALUES (s.ts_utc, s.region_code, s.metric, s.value, s.ingested_at)
            """,
            payload,
        )
        ctx.commit()
        return len(payload)
    finally:
        ctx.close()


def fetch_recent(
    region: str,
    metric: str = "carbon_intensity",
    limit: int = 24 * 30,
) -> List[Tuple[datetime, float]]:
    """Return list of (ts_utc, value) in chronological order."""
    with sqlite_conn() as conn:
        cur = conn.execute(
            """
            SELECT ts_utc, value
            FROM eia_hourly
            WHERE region_code = ? AND metric = ?
            ORDER BY ts_utc DESC
            LIMIT ?
            """,
            (region, metric, limit),
        )
        rows = cur.fetchall()

    out: List[Tuple[datetime, float]] = []
    for ts_str, value in rows:
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out.append((ts, float(value)))
    out.sort(key=lambda r: r[0])
    return out


def latest_value(region: str, metric: str = "carbon_intensity") -> Optional[Tuple[datetime, float]]:
    rows = fetch_recent(region, metric, limit=1)
    return rows[-1] if rows else None
