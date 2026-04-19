"""Health, readiness, and integration diagnostics."""

from __future__ import annotations

import importlib.util
import os
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
    sqlite_exists = sqlite_path.exists()
    sqlite_size = sqlite_path.stat().st_size if sqlite_exists else 0

    return {
        "time": datetime.now(timezone.utc).isoformat(),
        "env": s.app_env,
        "integrations": {
            "eia": {
                "configured": bool(s.eia_api_key),
                "note": "Without a key, ingest writes a deterministic mock series.",
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
        },
        "rag_corpus": {
            "path": "app/data/hf_corpus.json",
            "entries": _corpus_entry_count(),
        },
    }


def _corpus_entry_count() -> int:
    import json

    p = Path(__file__).resolve().parent.parent / "data" / "hf_corpus.json"
    try:
        return len(json.loads(p.read_text()).get("entries", []))
    except Exception:  # noqa: BLE001
        return -1
