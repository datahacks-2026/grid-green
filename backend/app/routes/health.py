"""Health, readiness, and integration diagnostics."""

from __future__ import annotations

import importlib.util
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/ping")
def ping() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.app_env,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/")
def root() -> dict:
    return {"service": "gridgreen-backend", "docs": "/docs", "ping": "/ping"}


def _eia_hourly_sqlite_stats(sqlite_path: Path) -> Dict[str, object]:
    """Read-only snapshot of local ``eia_hourly`` for judge / demo verification.

    Does not open Snowflake. Safe when the DB is missing or empty.
    """
    out: Dict[str, object] = {
        "table_found": False,
        "row_count": None,
        "distinct_regions": None,
        "ts_min_utc": None,
        "ts_max_utc": None,
        "note": None,
    }
    try:
        resolved = sqlite_path.expanduser()
        if not resolved.is_absolute():
            resolved = (Path.cwd() / resolved).resolve()
        else:
            resolved = resolved.resolve()
    except OSError as exc:
        out["note"] = f"sqlite_path_unusable:{exc}"
        return out

    if not resolved.exists():
        out["note"] = "sqlite_file_missing"
        return out

    try:
        conn = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        out["note"] = f"sqlite_open_failed:{exc}"
        return out

    try:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='eia_hourly'"
        )
        if cur.fetchone() is None:
            out["note"] = "eia_hourly_table_missing"
            return out
        out["table_found"] = True
        row = conn.execute("SELECT COUNT(*) FROM eia_hourly").fetchone()
        out["row_count"] = int(row[0]) if row and row[0] is not None else 0
        row = conn.execute("SELECT COUNT(DISTINCT region_code) FROM eia_hourly").fetchone()
        out["distinct_regions"] = int(row[0]) if row and row[0] is not None else 0
        row = conn.execute("SELECT MIN(ts_utc), MAX(ts_utc) FROM eia_hourly").fetchone()
        if row:
            out["ts_min_utc"] = row[0]
            out["ts_max_utc"] = row[1]
    except sqlite3.Error as exc:
        out["note"] = f"sqlite_query_failed:{exc}"
    finally:
        conn.close()
    return out


def _have(module: str) -> bool:
    """`find_spec` raises ModuleNotFoundError when a *parent* package is missing;
    treat that as "not installed" instead of bubbling the error to the caller."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


@router.get("/api/diagnostics")
def diagnostics() -> Dict[str, object]:
    """Report which integrations are configured, importable, and where data lives.

    This is intentionally cheap — it does *not* open Snowflake / Databricks
    connections (those can hang). Use the dedicated smoke scripts for live
    handshakes.
    """
    s = get_settings()

    sqlite_path = Path(s.sqlite_path)
    if not sqlite_path.is_absolute():
        sqlite_path = (Path.cwd() / sqlite_path).resolve()
    sqlite_exists = sqlite_path.exists()
    sqlite_size = sqlite_path.stat().st_size if sqlite_exists else 0
    eia_sqlite = _eia_hourly_sqlite_stats(sqlite_path)

    return {
        "time": datetime.now(timezone.utc).isoformat(),
        "env": s.app_env,
        "integrations": {
            "eia": {
                "configured": bool(s.eia_api_key),
                "note": (
                    "Without EIA_API_KEY, ingest still writes a deterministic mock series "
                    "so the app runs offline. For real EIA pulls, set the key and run "
                    "`python -m scripts.ingest_eia` from `backend/`, then confirm "
                    "`storage.eia_hourly.row_count` below."
                ),
            },
            "noaa": {"configured": bool(s.noaa_token)},
            "gemini": {
                "configured": bool(s.gemini_api_key),
                "package_installed": _have("google.generativeai"),
            },
            "snowflake": {
                "configured": s.use_snowflake,
                "package_installed": _have("snowflake.connector"),
                "database": s.snowflake_database,
                "schema": s.snowflake_schema,
            },
            "databricks_sql": {
                "configured": s.use_databricks_sql,
                "package_installed": _have("databricks.sql"),
                "bronze_table": s.databricks_bronze_table,
            },
            "databricks_sdk": {"package_installed": _have("databricks.sdk")},
            "wandb": {
                "configured": bool(s.wandb_api_key),
                "package_installed": _have("wandb"),
            },
            "huggingface": {
                "transformers": _have("transformers"),
                "sentence_transformers": _have("sentence_transformers"),
                "st_disabled": os.environ.get("GRIDGREEN_DISABLE_ST", "").strip().lower()
                in {"1", "true", "yes"},
            },
            "github_repo_fetcher": {
                "token_present": bool(
                    os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
                ),
            },
        },
        "storage": {
            "sqlite_path": str(sqlite_path),
            "sqlite_exists": sqlite_exists,
            "sqlite_size_bytes": sqlite_size,
            "eia_hourly": eia_sqlite,
        },
        "rag_corpus": {
            "path": "app/data/hf_corpus.json",
            "entries": _corpus_entry_count(),
        },
        "embedding_cache": _embedding_cache_status(),
    }


def _corpus_entry_count() -> int:
    import json

    p = Path(__file__).resolve().parent.parent / "data" / "hf_corpus.json"
    try:
        return len(json.loads(p.read_text()).get("entries", []))
    except Exception:  # noqa: BLE001
        return -1


def _embedding_cache_status() -> Dict[str, object]:
    """Surface the precomputed RAG embedding artifact in diagnostics."""
    try:
        from app.services import embedding_cache

        return embedding_cache.cache_status()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
