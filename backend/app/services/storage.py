"""Storage facade with Databricks/Snowflake/SQLite paths.

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

    # Always write SQLite so `fetch_recent` (read path used by the forecaster
    # and HTTP routes) sees ingested rows immediately. When Snowflake is
    # configured, we *also* write to Snowflake so it remains the canonical
    # warehouse for sponsor/judge evidence (`SELECT ... FROM eia_hourly`).
    n = _insert_sqlite(payload)

    if settings.use_snowflake:
        try:
            _insert_snowflake(payload)
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
            logger.warning(
                "Snowflake mirror failed (%s); SQLite write succeeded.%s", exc, hint
            )

    return n


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
    """Return list of (ts_utc, value) in chronological order.

    Runtime source is controlled by `GRIDGREEN_SERVE_FROM`:
    - `local`      : SQLite only
    - `databricks` : Databricks SQL first, fallback to SQLite on failure/empty
    - `auto`       : Databricks SQL first when configured, else SQLite
    """
    settings = get_settings()
    mode = (settings.gridgreen_serve_from or "local").strip().lower()
    rows: list[tuple[str, float]] = []

    use_databricks = mode == "databricks" or (mode == "auto" and settings.use_databricks_sql)
    if use_databricks:
        rows = _fetch_recent_databricks(region=region, metric=metric, limit=limit)
        if rows:
            return _normalize_rows(rows)

    rows = _fetch_recent_sqlite(region=region, metric=metric, limit=limit)
    return _normalize_rows(rows)


def _fetch_recent_sqlite(region: str, metric: str, limit: int) -> list[tuple[str, float]]:
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
        return [(str(ts), float(v)) for ts, v in cur.fetchall()]


def _fetch_recent_databricks(region: str, metric: str, limit: int) -> list[tuple[str, float]]:
    """Read recent rows from Databricks SQL table(s).

    Query order:
    1) `DATABRICKS_GOLD_TABLE` (if configured; no metric filter)
    2) `DATABRICKS_BRONZE_TABLE` (with metric filter)

    Falls back silently to SQLite callers on any connector/query issue/empty result.
    """
    settings = get_settings()
    tables = _databricks_candidate_tables()
    try:
        from databricks import sql as dbsql  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning("Databricks SQL connector unavailable (%s); using SQLite", exc)
        return []

    try:
        with dbsql.connect(
            server_hostname=settings.databricks_server_hostname or "",
            http_path=settings.databricks_http_path or "",
            access_token=settings.databricks_token or "",
        ) as conn:
            with conn.cursor() as cur:
                for table in tables:
                    if table == (settings.databricks_gold_table or "").strip():
                        # Gold table shape is expected to contain ts_utc, region_code, value
                        # and usually does not include a `metric` column.
                        cur.execute(
                            f"""
                            SELECT ts_utc, value
                            FROM {table}
                            WHERE region_code = ?
                            ORDER BY ts_utc DESC
                            LIMIT ?
                            """,
                            (region, limit),
                        )
                    else:
                        cur.execute(
                            f"""
                            SELECT ts_utc, value
                            FROM {table}
                            WHERE region_code = ? AND metric = ?
                            ORDER BY ts_utc DESC
                            LIMIT ?
                            """,
                            (region, metric, limit),
                        )
                    out: list[tuple[str, float]] = []
                    for ts, value in cur.fetchall():
                        out.append((str(ts), float(value)))
                    if out:
                        return out
                return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Databricks read failed (%s); using SQLite", exc)
        return []


def _databricks_candidate_tables() -> list[str]:
    """Databricks read priority for runtime serving."""
    s = get_settings()
    out: list[str] = []
    gold = (s.databricks_gold_table or "").strip()
    if gold:
        out.append(gold)
    out.append(s.databricks_bronze_table)
    return out


def _normalize_rows(rows: list[tuple[str, float]]) -> List[Tuple[datetime, float]]:
    """Normalize timestamp strings into UTC datetimes and sort ascending."""

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
