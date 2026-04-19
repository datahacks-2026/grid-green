"""Smoke tests: scaffold-level correctness for Person A's slice.

Run from `backend/`:
    pytest -q
"""

from __future__ import annotations

import os

os.environ.setdefault("CORS_ALLOW_ORIGINS", "http://localhost:3000")
# Disable rate limiting noise in tests by raising the cap; doesn't change shapes.
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "100000")
# Hugging Face model downloads are flaky in CI / proxied networks — keep RAG on TF-IDF.
os.environ.setdefault("GRIDGREEN_DISABLE_ST", "1")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health + grid
# ---------------------------------------------------------------------------

def test_ping() -> None:
    r = client.get("/ping")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_check_grid_default_region() -> None:
    r = client.get("/api/check_grid")
    assert r.status_code == 200
    body = r.json()
    assert body["region"] == "CISO"
    assert body["current_gco2_kwh"] > 0
    assert body["trend"] in {"rising", "falling", "flat"}


def test_find_clean_window_shape() -> None:
    r = client.get("/api/find_clean_window", params={"region": "CISO", "hours_needed": 4})
    assert r.status_code == 200
    body = r.json()
    assert "optimal_start" in body
    assert "expected_gco2_kwh" in body
    assert "current_gco2_kwh" in body
    assert "co2_savings_pct" in body
    assert isinstance(body["forecast_48h"], list)
    assert len(body["forecast_48h"]) >= 1


# ---------------------------------------------------------------------------
# Estimator
# ---------------------------------------------------------------------------

def test_estimate_carbon_with_known_model() -> None:
    code = """
from transformers import AutoModel
model = AutoModel.from_pretrained('google/flan-t5-large')
model.fit(x, y, epochs=3, batch_size=16)
""".strip()
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["co2_grams_now"] >= 0
    assert body["confidence"] in {"low", "medium", "high"}
    assert any(p["pattern"] == "from_pretrained" for p in body["detected_patterns"])


def test_estimate_carbon_rejects_oversized_payload() -> None:
    big_code = "x = 1\n" * 200_000
    r = client.post("/api/estimate_carbon", json={"code": big_code, "region": "CISO"})
    assert r.status_code == 413


def test_estimate_carbon_rejects_bad_region() -> None:
    r = client.post("/api/estimate_carbon", json={"code": "print(1)", "region": "ZZZZ"})
    # Pydantic enum rejection happens at validation → 422.
    assert r.status_code in {400, 422}


# ---------------------------------------------------------------------------
# Phase 5 — RAG / suggest_greener
# ---------------------------------------------------------------------------

def test_suggest_greener_returns_real_alternative() -> None:
    code = """
from transformers import AutoModelForSeq2SeqLM
m = AutoModelForSeq2SeqLM.from_pretrained('google/flan-t5-xxl')
""".strip()
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected at least one greener suggestion for flan-t5-xxl"
    s = suggestions[0]
    assert s["alternative_snippet"] != s["original_snippet"]
    assert 0 < s["carbon_saved_pct"] <= 100
    assert 0 < s["performance_retained_pct"] <= 100
    assert s["citation"]


def test_suggest_greener_no_models_returns_empty() -> None:
    r = client.post("/api/suggest_greener", json={"code": "print('hello world')"})
    assert r.status_code == 200
    assert r.json()["suggestions"] == []


def test_suggest_greener_detects_openai_api_model() -> None:
    code = (
        "from openai import OpenAI\n"
        "client = OpenAI()\n"
        "resp = client.chat.completions.create(model='gpt-4-turbo', messages=[])\n"
    )
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected greener API-model swap for gpt-4-turbo"
    assert "gpt-4o-mini" in suggestions[0]["alternative_snippet"].lower()


def test_suggest_greener_detects_assignment_literal() -> None:
    code = 'MODEL_ID = "meta-llama/Llama-3-70B"\n'
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected greener swap for Llama-3-70B literal"
    assert "llama-3-8b" in suggestions[0]["alternative_snippet"].lower()


def test_suggest_greener_detects_pipeline_kwarg() -> None:
    code = "from transformers import pipeline\np = pipeline('text-generation', model='mistralai/Mixtral-8x7B-v0.1')\n"
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected greener swap for Mixtral-8x7B"
    assert "mistral-7b" in suggestions[0]["alternative_snippet"].lower()


def test_suggest_greener_merges_part_a_context_into_reasoning() -> None:
    code = (
        "from transformers import AutoModelForSeq2SeqLM\n"
        "m = AutoModelForSeq2SeqLM.from_pretrained('google/flan-t5-xxl')\n"
    )
    r = client.post(
        "/api/suggest_greener",
        json={
            "code": code,
            "region": "CISO",
            "current_gco2_kwh": 455.2,
            "co2_grams_now": 900.0,
            "co2_grams_optimal": 200.0,
            "co2_savings_pct_window": 40.0,
            "optimal_window_start": "2026-01-01T03:00:00Z",
            "impact_focus_lines": [2],
        },
    )
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions
    reasoning = suggestions[0]["reasoning"]
    assert "CISO" in reasoning
    assert "455" in reasoning or "455.2" in reasoning


def test_scorecard_event_roundtrip() -> None:
    import uuid

    sid = f"pytest-{uuid.uuid4().hex}"
    r0 = client.get("/api/scorecard", params={"session_id": sid})
    assert r0.status_code == 200
    assert r0.json()["suggestions_accepted"] == 0
    r1 = client.post(
        "/api/scorecard/event",
        json={"session_id": sid, "event": "suggestion_accepted", "co2_saved_grams": 12.5},
    )
    assert r1.status_code == 200
    assert r1.json()["suggestions_accepted"] == 1
    assert r1.json()["co2_saved_grams"] == 12.5


# ---------------------------------------------------------------------------
# Optional context routes
# ---------------------------------------------------------------------------

def test_campus_heat_summary_uses_sample_csv() -> None:
    r = client.get("/api/context/campus_heat")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "scripps_ucsd_mobile_weather"
    assert body["n_points"] > 0
    assert body["n_stations"] >= 1
    assert body["mean_temperature_c"] is not None


# ---------------------------------------------------------------------------
# MCP server module imports + tool registration
# ---------------------------------------------------------------------------

def test_mcp_server_imports_and_registers_tools() -> None:
    import mcp_server

    # Internal: FastMCP exposes a list of registered tools.
    tools = mcp_server.mcp._tool_manager.list_tools()  # type: ignore[attr-defined]
    names = {t.name for t in tools}
    assert {"check_grid", "find_clean_window", "estimate_carbon", "suggest_greener"}.issubset(names)


# ---------------------------------------------------------------------------
# DLT pipeline (local fallback path)
# ---------------------------------------------------------------------------

def test_dlt_local_runs_without_data() -> None:
    # Just ensure the script imports and run_local() handles empty data
    # without raising. Real run is exercised after ingestion.
    from scripts import dlt_pipeline

    dlt_pipeline.run_local()


# ---------------------------------------------------------------------------
# Diagnostics + repo analyzer
# ---------------------------------------------------------------------------

def test_diagnostics_reports_known_keys() -> None:
    r = client.get("/api/diagnostics")
    assert r.status_code == 200
    body = r.json()
    assert "integrations" in body
    integrations = body["integrations"]
    for k in ("eia", "noaa", "gemini", "snowflake", "databricks_sql", "huggingface"):
        assert k in integrations
    assert body["rag_corpus"]["entries"] >= 1


def test_analyze_repo_rejects_non_github_url() -> None:
    r = client.post(
        "/api/analyze_repo",
        json={"repo_url": "https://example.com/not/a/repo"},
    )
    assert r.status_code == 400


def test_aggregate_repo_sources_byte_cap() -> None:
    from app.routes.repo import _aggregate_repo_sources
    from app.services.repo_fetcher import RepoFile

    files = [
        RepoFile(path="a.py", content="x" * 4000),
        RepoFile(path="b.py", content="y" * 4000),
    ]
    agg = _aggregate_repo_sources(files, max_code_bytes=200)
    assert len(agg.text.encode("utf-8")) <= 200
    assert agg.truncated
    assert agg.file_count >= 1


def test_repo_fetcher_extracts_python_from_notebook() -> None:
    import json as _json

    from app.services.repo_fetcher import extract_python_from_notebook

    nb = {
        "cells": [
            {"cell_type": "markdown", "source": "ignore me"},
            {
                "cell_type": "code",
                "source": ["from transformers import AutoModel\n", "AutoModel.from_pretrained('bert-large-uncased')\n"],
            },
        ]
    }
    code = extract_python_from_notebook(_json.dumps(nb))
    assert "from_pretrained" in code
    assert "ignore me" not in code
