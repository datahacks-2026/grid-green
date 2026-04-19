"""Optional Hugging Face Hub lookups for dynamic greener suggestions.

When the curated RAG corpus has no exact ``from`` match, we can still call
the public ``GET https://huggingface.co/api/models/{repo_id}`` endpoint to
read ``safetensors`` parameter counts, ``pipeline_tag``, and ``tags``, then
propose a smaller *class* of checkpoint (today: sentence-similarity →
MiniLM) with savings derived from reported parameter totals.

Disable in tests or air-gapped env::

    GRIDGREEN_DISABLE_HF_HUB=1

Optional auth for private/gated models::

    HF_TOKEN=...   # or HUGGING_FACE_HUB_TOKEN
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

HF_MODELS_API = "https://huggingface.co/api/models"

# Canonical “small but useful” sentence embedding used elsewhere in GridGreen.
EMBEDDING_FALLBACK_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
_EMBEDDING_FALLBACK_PARAMS_B = 0.022


@dataclass(frozen=True)
class HubModelBrief:
    model_id: str
    params_b: float | None
    pipeline_tag: str | None
    library_name: str | None
    tags: tuple[str, ...]


@dataclass(frozen=True)
class DynamicSwapPlan:
    """Payload for :meth:`app.services.rag.RagIndex.suggest` to turn into a ``Suggestion``."""

    line: int
    original_snippet: str
    alternative_snippet: str
    carbon_saved_pct: int
    performance_retained_pct: int
    citation: str
    reasoning: str


def _hub_disabled() -> bool:
    return os.environ.get("GRIDGREEN_DISABLE_HF_HUB", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _auth_headers() -> dict[str, str]:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token and token.strip():
        return {"Authorization": f"Bearer {token.strip()}"}
    return {}


@lru_cache(maxsize=256)
def _fetch_hub_model_brief_cached(cache_key: str) -> HubModelBrief | None:
    """Network + JSON parse; cache key is the ``repo_id`` string passed to the Hub API."""
    url = f"{HF_MODELS_API}/{cache_key}"
    try:
        with httpx.Client(timeout=2.5, follow_redirects=True) as client:
            r = client.get(url, headers=_auth_headers())
    except Exception as exc:  # noqa: BLE001
        logger.info("HF Hub fetch failed for %s: %s", cache_key, exc)
        return None
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        logger.info("HF Hub %s returned HTTP %s", cache_key, r.status_code)
        return None
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return None

    params_b: float | None = None
    st = data.get("safetensors")
    if isinstance(st, dict) and "total" in st:
        try:
            params_b = float(st["total"]) / 1e9
        except (TypeError, ValueError):
            params_b = None

    raw_tags = data.get("tags")
    if isinstance(raw_tags, list):
        tags_t = tuple(str(t) for t in raw_tags)
    else:
        tags_t = ()

    mid = data.get("id") or cache_key
    return HubModelBrief(
        model_id=str(mid),
        params_b=params_b,
        pipeline_tag=data.get("pipeline_tag"),
        library_name=data.get("library_name"),
        tags=tags_t,
    )


def fetch_hub_model_brief(model_id: str) -> HubModelBrief | None:
    """Return Hub metadata for ``org/model`` ids, or ``None`` if unavailable."""
    mid = model_id.strip()
    if not mid or "/" not in mid:
        return None
    if _hub_disabled():
        return None
    return _fetch_hub_model_brief_cached(mid)


def _replace_model_id_in_snippet(snippet: str, old_id: str, new_id: str) -> str:
    pat = re.compile(re.escape(old_id), re.IGNORECASE)
    if pat.search(snippet):
        return pat.sub(new_id, snippet, count=1)
    return f"{snippet}  # try: {new_id}"


def _norm_model_id(s: str) -> str:
    return s.lower().split(":", 1)[0].strip()


def _is_sentence_embedding_task(brief: HubModelBrief) -> bool:
    tags_l = [t.lower() for t in brief.tags]
    pt = (brief.pipeline_tag or "").lower()
    lib = (brief.library_name or "").lower()
    if pt in {"sentence-similarity", "feature-extraction"}:
        return True
    if "sentence-similarity" in tags_l or "feature-extraction" in tags_l:
        return True
    return lib == "sentence-transformers" and (
        "sentence-similarity" in tags_l or "feature-extraction" in tags_l
    )


def plan_embedding_downgrade_from_hub(
    line: int,
    snippet: str,
    model_id: str,
) -> Optional[DynamicSwapPlan]:
    """If Hub says this is a sentence embedding model and params > MiniLM, plan a swap."""
    brief = fetch_hub_model_brief(model_id)
    if brief is None:
        return None
    if not _is_sentence_embedding_task(brief):
        return None
    if _norm_model_id(model_id) == _norm_model_id(EMBEDDING_FALLBACK_MODEL_ID):
        return None

    from_b = brief.params_b
    if from_b is None or from_b <= 0:
        from_b = 0.08
    to_b = _EMBEDDING_FALLBACK_PARAMS_B
    if from_b <= to_b * 1.05:
        return None

    carbon_saved = int(min(90, max(8, round(100 * (1 - to_b / from_b)))))
    perf = 78 if from_b > 0.2 else 85

    alt = _replace_model_id_in_snippet(snippet, model_id, EMBEDDING_FALLBACK_MODEL_ID)
    params_note = (
        f"~{brief.params_b:.2f}B parameters reported on the Hub"
        if brief.params_b
        else "parameter count not published; using a conservative baseline"
    )
    reasoning = (
        f"No exact curated swap exists for `{brief.model_id}`; using live Hugging Face "
        f"metadata ({params_note}). `{EMBEDDING_FALLBACK_MODEL_ID}` is far smaller for "
        "generic sentence embeddings — re-run retrieval / safety metrics on your domain "
        "before adopting."
    )
    citation = (
        f"Hugging Face model card API — https://huggingface.co/{brief.model_id} "
        "(pipeline_tag + safetensors totals)."
    )
    return DynamicSwapPlan(
        line=line,
        original_snippet=snippet,
        alternative_snippet=alt,
        carbon_saved_pct=carbon_saved,
        performance_retained_pct=perf,
        citation=citation,
        reasoning=reasoning,
    )


def clear_hub_cache() -> None:
    """Test helper: bust ``lru_cache`` after monkeypatching HTTP."""
    _fetch_hub_model_brief_cached.cache_clear()
