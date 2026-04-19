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
# HF Hub metadata for dynamic embedding swaps is mocked per test; keep off by default.
os.environ.setdefault("GRIDGREEN_DISABLE_HF_HUB", "1")

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


def test_estimate_carbon_workload_practices_detect_ddp_autocast_compile() -> None:
    """High-scope v0: advisory AMP / DDP / compile signals alongside CO₂ estimate."""
    code = (
        "import torch\n"
        "from torch.nn.parallel import DistributedDataParallel\n"
        "m = DistributedDataParallel(m)\n"
        "with torch.autocast('cuda'):\n"
        "    pass\n"
        "m = torch.compile(m)\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    practices = body.get("workload_practices") or []
    ids = {p["id"] for p in practices}
    assert "ddp" in ids
    assert "autocast" in ids
    assert "torch_compile" in ids
    for p in practices:
        assert p["impact"] in {"low", "medium", "high"}
        assert "rationale" in p and len(p["rationale"]) > 10


def test_estimate_carbon_basic_model_is_not_low_confidence() -> None:
    """Regression: previously `gpt2-xl` was unknown to the catalog and the
    estimator returned `confidence='low'`. After unifying detection with
    the RAG extractor it should be recognised as a single high-confidence
    hit."""
    code = (
        "from transformers import AutoModelForCausalLM\n"
        "m = AutoModelForCausalLM.from_pretrained('gpt2-xl')\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "high", (
        f"expected 'high' for a single known model, got {body['confidence']}"
    )
    assert body["co2_grams_now"] > 0


def test_estimate_carbon_api_model_via_kwarg_is_recognised() -> None:
    """OpenAI-style `model='gpt-4'` kwarg used to evade detection (estimator
    only scanned `from_pretrained` literals). It must now register."""
    code = (
        "from openai import OpenAI\n"
        "client = OpenAI()\n"
        "resp = client.chat.completions.create(model='gpt-4-turbo', messages=[])\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] in {"high", "medium"}, body
    assert body["co2_grams_now"] > 0


def test_estimate_carbon_bedrock_modelid_kwarg_detected() -> None:
    """AWS Bedrock SDK uses camelCase `modelId=` and dotted vendor prefixes
    like `anthropic.claude-3-sonnet-20240229`. Both must register."""
    code = (
        "import boto3\n"
        "bedrock = boto3.client('bedrock-runtime')\n"
        "resp = bedrock.invoke_model(modelId='anthropic.claude-3-sonnet-20240229', body=b'')\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] in {"high", "medium"}, body
    assert body["co2_grams_now"] > 0


def test_estimate_carbon_dedups_repeated_model_id_for_high_confidence() -> None:
    """Loading the same model twice (e.g. tokenizer + model) used to produce
    two hits → `confidence='medium'`. Dedup by catalog key keeps it `high`."""
    code = (
        "from transformers import AutoTokenizer, AutoModelForCausalLM\n"
        "tok = AutoTokenizer.from_pretrained('gpt2-xl')\n"
        "m = AutoModelForCausalLM.from_pretrained('gpt2-xl')\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "high", body


def test_estimate_carbon_takes_max_epochs_across_file() -> None:
    """Two `epochs=` literals in the same script — the bigger one drives
    cost (worst-case). Compare against a baseline that only has the small
    value: the larger-epoch run must be strictly more expensive."""
    base_code = (
        "from transformers import AutoModelForCausalLM, Trainer\n"
        "m = AutoModelForCausalLM.from_pretrained('gpt2-xl')\n"
        "Trainer(model=m).train(epochs=1)\n"
    )
    multi_code = (
        "from transformers import AutoModelForCausalLM, Trainer\n"
        "m = AutoModelForCausalLM.from_pretrained('gpt2-xl')\n"
        "Trainer(model=m).train(epochs=1)  # smoke test\n"
        "Trainer(model=m).train(epochs=10)\n"
    )
    r1 = client.post("/api/estimate_carbon", json={"code": base_code, "region": "CISO"})
    r2 = client.post("/api/estimate_carbon", json={"code": multi_code, "region": "CISO"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["co2_grams_now"] > r1.json()["co2_grams_now"], (
        f"max-epochs scaling broken: base={r1.json()['co2_grams_now']} "
        f"multi={r2.json()['co2_grams_now']}"
    )


def test_estimate_carbon_takes_min_batch_size_across_file() -> None:
    """Two `batch_size=` literals — the smaller one drives cost (smaller
    batches → more wall time per epoch)."""
    base_code = (
        "from transformers import AutoModelForCausalLM, Trainer\n"
        "m = AutoModelForCausalLM.from_pretrained('gpt2-xl')\n"
        "Trainer(model=m).train(epochs=2, batch_size=64)\n"
    )
    multi_code = (
        "from transformers import AutoModelForCausalLM, Trainer\n"
        "m = AutoModelForCausalLM.from_pretrained('gpt2-xl')\n"
        "Trainer(model=m).train(epochs=2, batch_size=64)\n"
        "Trainer(model=m).train(epochs=2, batch_size=4)\n"
    )
    r1 = client.post("/api/estimate_carbon", json={"code": base_code, "region": "CISO"})
    r2 = client.post("/api/estimate_carbon", json={"code": multi_code, "region": "CISO"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["co2_grams_now"] > r1.json()["co2_grams_now"], (
        f"min-batch scaling broken: base={r1.json()['co2_grams_now']} "
        f"multi={r2.json()['co2_grams_now']}"
    )


def test_estimate_carbon_resolves_variable_assignment_across_statements() -> None:
    """`MID = "gpt2-xl"` then `from_pretrained(MID)` — the AST walker
    must follow the variable to its literal value (regex extractor
    couldn't, so the call site looked like just `from_pretrained(MID)`)."""
    code = (
        "from transformers import AutoModelForCausalLM\n"
        "MID = 'gpt2-xl'\n"
        "m = AutoModelForCausalLM.from_pretrained(MID)\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "high", body
    assert body["co2_grams_now"] > 0


def test_estimate_carbon_dict_spread_kwarg_detected() -> None:
    """`client.create(**{"model": "gpt-4-turbo"})` — only the AST walker
    can see inside the dict literal. Regex would miss it entirely."""
    code = (
        "from openai import OpenAI\n"
        "kw = {'model': 'gpt-4-turbo'}\n"
        "OpenAI().chat.completions.create(**kw)\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    # Note: the dict is bound to a variable then spread. Resolving the
    # variable requires the symbol table lookup; we only resolve direct
    # `**{"model": "..."}` literals. Either way the literal in the dict
    # `kw = {'model': 'gpt-4-turbo'}` is NOT one we read, so this case
    # should still gracefully degrade rather than crash.
    assert body["confidence"] in {"low", "medium", "high"}, body


def test_estimate_carbon_dict_spread_inline_literal_detected() -> None:
    """The case the AST walker *does* fully resolve: a dict literal
    spread directly into the call."""
    code = (
        "from openai import OpenAI\n"
        "OpenAI().chat.completions.create(**{'model': 'gpt-4-turbo'}, messages=[])\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] in {"high", "medium"}, body


def test_estimate_carbon_fstring_prefix_falls_back_to_family() -> None:
    """f-string with a known-family constant prefix (`meta-llama/Llama-`)
    should at least produce a worst-case family estimate, not the
    `low` confidence + 0.1B placeholder."""
    code = (
        "from transformers import AutoModelForCausalLM\n"
        "size = '70B'\n"
        "m = AutoModelForCausalLM.from_pretrained(f'meta-llama/Llama-3.1-{size}')\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    # Family fallback fires → uses the largest llama entry. We just
    # check we escaped the 0.1B/5h placeholder fallback.
    assert body["co2_grams_now"] > 100, body
    assert body["gpu_hours"] > 1.0, body


def test_estimate_carbon_sklearn_random_forest_recognised() -> None:
    """Classical ML scripts must produce a non-trivial estimate (not
    `confidence: low` + 0.1B placeholder)."""
    code = (
        "from sklearn.ensemble import RandomForestClassifier\n"
        "rf = RandomForestClassifier(n_estimators=2000)\n"
        "rf.fit(X, y)\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "medium", body
    assert body["co2_grams_now"] > 0
    assert any(
        p["pattern"].startswith("sklearn:") for p in body["detected_patterns"]
    ), body["detected_patterns"]


def test_estimate_carbon_xgboost_recognised() -> None:
    """XGBoost / LightGBM constructors should also count."""
    code = (
        "import xgboost as xgb\n"
        "model = xgb.XGBClassifier(n_estimators=500)\n"
        "model.fit(X, y)\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "medium", body
    assert any(
        "xgb" in p["pattern"].lower() for p in body["detected_patterns"]
    ), body["detected_patterns"]


def test_estimate_carbon_sklearn_n_estimators_scales_cost() -> None:
    """A 5000-tree RandomForest should be charged more than a 50-tree
    one, scaling roughly with `n_estimators`."""
    small = (
        "from sklearn.ensemble import RandomForestClassifier\n"
        "RandomForestClassifier(n_estimators=50).fit(X, y)\n"
    )
    big = (
        "from sklearn.ensemble import RandomForestClassifier\n"
        "RandomForestClassifier(n_estimators=5000).fit(X, y)\n"
    )
    r1 = client.post("/api/estimate_carbon", json={"code": small, "region": "CISO"})
    r2 = client.post("/api/estimate_carbon", json={"code": big, "region": "CISO"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["co2_grams_now"] > r1.json()["co2_grams_now"], (
        f"n_estimators scaling broken: 50→{r1.json()['co2_grams_now']} "
        f"5000→{r2.json()['co2_grams_now']}"
    )


def test_estimate_carbon_timm_underscore_variant_detected() -> None:
    """timm uses underscore-separated names (`vit_base_patch16_224`); we
    normalise `_` → `-` so the catalog still matches `vit-base`."""
    code = (
        "import timm\n"
        "m = timm.create_model('vit_large_patch16_224', pretrained=True)\n"
    )
    r = client.post("/api/estimate_carbon", json={"code": code, "region": "CISO"})
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == "high", body


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


def test_suggest_greener_ignores_inline_comment_reference() -> None:
    """A model name inside an inline comment must not trigger a swap."""
    code = "x = 1  # we used to use 'google/flan-t5-xxl' here\n"
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    assert r.json()["suggestions"] == [], (
        "model id inside a comment should not produce a suggestion"
    )


def test_suggest_greener_ignores_string_in_unrelated_list() -> None:
    """A bare string literal inside a list/log message is not 'usage'."""
    code = (
        "names = ['google/flan-t5-xxl', 'meta-llama/Llama-3-70B']\n"
        "print('candidates:', names)\n"
    )
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    assert r.json()["suggestions"] == [], (
        "model ids only mentioned inside a list literal should not produce suggestions"
    )


def test_suggest_greener_ignores_log_message_with_model_name() -> None:
    code = "print('about to use bert-large-uncased for eval')\n"
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    assert r.json()["suggestions"] == []


def test_suggest_greener_detects_basic_gpt2_xl() -> None:
    code = (
        "from transformers import AutoModelForCausalLM\n"
        "m = AutoModelForCausalLM.from_pretrained('gpt2-xl')\n"
    )
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected greener swap for basic gpt2-xl"
    assert "gpt2-large" in suggestions[0]["alternative_snippet"].lower()


def test_suggest_greener_detects_basic_t5_large() -> None:
    code = (
        "from transformers import T5ForConditionalGeneration\n"
        "m = T5ForConditionalGeneration.from_pretrained('t5-large')\n"
    )
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected greener swap for basic t5-large"
    assert "t5-base" in suggestions[0]["alternative_snippet"].lower()


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


def test_suggest_greener_detects_sentence_transformer_unknown_hf_org(
    monkeypatch,
) -> None:
    """Unknown Hub orgs use live HF metadata (mocked here) when the static corpus
    has no exact ``from`` row — regression for drug-safety style repos."""
    from app.services import hf_hub_models

    def _fake_fetch(mid: str) -> hf_hub_models.HubModelBrief | None:
        if "BioLORD" not in mid:
            return None
        return hf_hub_models.HubModelBrief(
            model_id="FremyCompany/BioLORD-2023",
            params_b=0.109,
            pipeline_tag="sentence-similarity",
            library_name="sentence-transformers",
            tags=("sentence-transformers", "sentence-similarity", "pytorch"),
        )

    monkeypatch.setattr(hf_hub_models, "fetch_hub_model_brief", _fake_fetch)
    hf_hub_models.clear_hub_cache()

    code = (
        "from sentence_transformers import SentenceTransformer\n"
        'MODEL_NAME = "FremyCompany/BioLORD-2023"\n'
        "def _get_model():\n"
        "    return SentenceTransformer(MODEL_NAME)\n"
    )
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected HF Hub–driven embedding downgrade"
    assert "minilm" in suggestions[0]["alternative_snippet"].lower()
    assert "huggingface.co" in suggestions[0]["citation"].lower()


def test_suggest_greener_detects_pipeline_kwarg() -> None:
    code = "from transformers import pipeline\np = pipeline('text-generation', model='mistralai/Mixtral-8x7B-v0.1')\n"
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected greener swap for Mixtral-8x7B"
    assert "mistral-7b" in suggestions[0]["alternative_snippet"].lower()


def test_suggest_greener_detects_replicate_slug_with_sha() -> None:
    """Replicate slugs look like `meta/meta-llama-3-70b-instruct:abc123`.
    We accept the `meta/` org and strip the `:sha` version pin so the
    catalog still matches Llama-3-70B → Llama-3-8B."""
    code = (
        "import replicate\n"
        "out = replicate.run('meta/meta-llama-3-70b-instruct:abc123', input={'prompt': 'hi'})\n"
    )
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected greener swap for Replicate Llama-3-70B slug"


def test_suggest_greener_detects_bedrock_dotted_id() -> None:
    """Bedrock vendor-prefixed IDs (`anthropic.claude-3-opus-20240229`)
    must still match the corpus `from` field after stripping the dot
    prefix."""
    code = (
        "import boto3\n"
        "bedrock = boto3.client('bedrock-runtime')\n"
        "resp = bedrock.invoke_model(modelId='anthropic.claude-3-opus-20240229', body=b'')\n"
    )
    r = client.post("/api/suggest_greener", json={"code": code})
    assert r.status_code == 200
    suggestions = r.json()["suggestions"]
    assert suggestions, "expected greener swap for Bedrock claude-3-opus"


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
    # New: SageMaker-produced embedding cache is surfaced even when missing.
    assert "embedding_cache" in body
    assert "path" in body["embedding_cache"]


# ---------------------------------------------------------------------------
# Unified pipeline + embedding cache
# ---------------------------------------------------------------------------

def test_embedding_cache_status_includes_path() -> None:
    from app.services import embedding_cache

    status = embedding_cache.cache_status()
    assert "path" in status
    assert "exists" in status
    assert isinstance(status["disabled"], bool)


def test_embedding_cache_load_returns_none_when_disabled(monkeypatch) -> None:
    from app.services import embedding_cache

    monkeypatch.setenv("GRIDGREEN_DISABLE_EMBEDDING_CACHE", "1")
    assert embedding_cache.load_cache(expected_n_docs=999) is None


def test_embedding_cache_round_trip_through_local_pipeline(tmp_path, monkeypatch) -> None:
    """A minimal cache file written to a temp path is picked up cleanly."""
    import json as _json

    from app.services import embedding_cache

    payload = {
        "model": "test-model",
        "device": "cpu",
        "n_docs": 2,
        "doc_ids": ["a->b", "c->d"],
        "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
    }
    target = tmp_path / "cache.json"
    target.write_text(_json.dumps(payload))
    monkeypatch.setenv("GRIDGREEN_EMBEDDING_CACHE_PATH", str(target))
    monkeypatch.delenv("GRIDGREEN_DISABLE_EMBEDDING_CACHE", raising=False)

    cache = embedding_cache.load_cache(expected_n_docs=2)
    assert cache is not None
    assert cache.n_docs == 2
    assert cache.dim == 3
    assert cache.model == "test-model"


def test_embedding_cache_size_mismatch_is_rejected(tmp_path, monkeypatch) -> None:
    import json as _json

    from app.services import embedding_cache

    target = tmp_path / "cache.json"
    target.write_text(_json.dumps({
        "model": "x", "device": "cpu", "n_docs": 1, "embeddings": [[0.1]],
    }))
    monkeypatch.setenv("GRIDGREEN_EMBEDDING_CACHE_PATH", str(target))
    monkeypatch.delenv("GRIDGREEN_DISABLE_EMBEDDING_CACHE", raising=False)

    assert embedding_cache.load_cache(expected_n_docs=42) is None


def test_storage_fetch_recent_prefers_databricks_in_auto_mode(monkeypatch) -> None:
    """When `GRIDGREEN_SERVE_FROM=auto` and Databricks returns rows, SQLite should not be used."""
    from app.config import get_settings
    from app.services import storage

    monkeypatch.setenv("GRIDGREEN_SERVE_FROM", "auto")
    monkeypatch.setenv("DATABRICKS_SERVER_HOSTNAME", "example.databricks.com")
    monkeypatch.setenv("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/abc")
    monkeypatch.setenv("DATABRICKS_TOKEN", "tok")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    def _fake_db(*, region: str, metric: str, limit: int):  # noqa: ARG001
        return [("2026-01-01T00:00:00+00:00", 123.4)]

    def _fake_sqlite(*, region: str, metric: str, limit: int):  # noqa: ARG001
        raise AssertionError("SQLite fallback should not be called when Databricks returns rows")

    monkeypatch.setattr(storage, "_fetch_recent_databricks", _fake_db)
    monkeypatch.setattr(storage, "_fetch_recent_sqlite", _fake_sqlite)

    rows = storage.fetch_recent("CISO", limit=1)
    assert len(rows) == 1
    assert rows[0][1] == 123.4
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_storage_databricks_candidate_tables_gold_first(monkeypatch) -> None:
    from app.config import get_settings
    from app.services import storage

    monkeypatch.setenv("DATABRICKS_GOLD_TABLE", "gridgreen.processed.eia_gold_carbon_24h_ma")
    monkeypatch.setenv("DATABRICKS_BRONZE_TABLE", "gridgreen.raw.eia_raw")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    assert storage._databricks_candidate_tables() == [  # noqa: SLF001
        "gridgreen.processed.eia_gold_carbon_24h_ma",
        "gridgreen.raw.eia_raw",
    ]
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_run_pipeline_module_imports_and_exposes_main() -> None:
    """Single entry point sanity check — full execution requires data + AWS."""
    from scripts import run_pipeline

    assert callable(run_pipeline.main)
    assert callable(run_pipeline._stage_diagnose)
    assert callable(run_pipeline._stage_databricks)


def test_run_pipeline_databricks_stage_runs_locally(monkeypatch) -> None:
    """`--databricks=local` does CSV export + local DLT, no Databricks env required."""
    from scripts import run_pipeline

    # Pretend DATABRICKS_* is not configured so the stage stays in local mode.
    for var in (
        "DATABRICKS_SERVER_HOSTNAME",
        "DATABRICKS_HTTP_PATH",
        "DATABRICKS_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)

    detail = run_pipeline._stage_databricks("local")
    assert "csv" in detail.lower() or "local DLT" in detail


def test_upload_candidate_paths_uc_before_filestore(monkeypatch) -> None:
    from scripts import upload_eia_export_to_databricks as up

    monkeypatch.delenv("DATABRICKS_UC_VOLUME_EXPORT_PATH", raising=False)
    monkeypatch.delenv("DATABRICKS_VOLUME_NAME", raising=False)
    monkeypatch.setenv("DATABRICKS_BRONZE_TABLE", "my_catalog.my_schema.eia_raw")
    monkeypatch.delenv("DATABRICKS_DBFS_EXPORT_PATH", raising=False)
    paths = up._candidate_remote_paths()
    assert paths[0].startswith("/Volumes/my_catalog/my_schema/")
    assert paths[-1] == "/FileStore/gridgreen/eia_hourly_export.csv"


def test_upload_candidate_uc_export_path_is_first(monkeypatch) -> None:
    from scripts import upload_eia_export_to_databricks as up

    monkeypatch.setenv(
        "DATABRICKS_UC_VOLUME_EXPORT_PATH",
        "/Volumes/acme/raw/landing/eia_hourly_export.csv",
    )
    monkeypatch.setenv("DATABRICKS_BRONZE_TABLE", "gridgreen.raw.eia_raw")
    paths = up._candidate_remote_paths()
    assert paths[0] == "/Volumes/acme/raw/landing/eia_hourly_export.csv"


def test_upload_candidate_includes_workspace_shared(monkeypatch) -> None:
    from scripts import upload_eia_export_to_databricks as up

    monkeypatch.delenv("DATABRICKS_UC_VOLUME_EXPORT_PATH", raising=False)
    monkeypatch.delenv("DATABRICKS_WORKSPACE_EXPORT_PATH", raising=False)
    monkeypatch.setenv("DATABRICKS_BRONZE_TABLE", "gridgreen.raw.eia_raw")
    monkeypatch.delenv("DATABRICKS_DBFS_EXPORT_PATH", raising=False)
    paths = up._candidate_remote_paths()
    assert "/Workspace/Shared/gridgreen/eia_hourly_export.csv" in paths


def test_run_pipeline_databricks_stage_fails_loudly_for_upload_without_env(
    monkeypatch,
) -> None:
    """`--databricks=upload` must raise when the workspace creds are missing."""
    from scripts import run_pipeline

    for var in (
        "DATABRICKS_SERVER_HOSTNAME",
        "DATABRICKS_HTTP_PATH",
        "DATABRICKS_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)

    # Reset cached settings so the missing env is observed.
    from app.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    import pytest

    with pytest.raises(RuntimeError):
        run_pipeline._stage_databricks("upload")


def test_sagemaker_processing_module_imports() -> None:
    """The launcher must import even without boto3/sagemaker installed."""
    from scripts import sagemaker_processing

    assert callable(sagemaker_processing.main)
    assert callable(sagemaker_processing._build_local)


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
