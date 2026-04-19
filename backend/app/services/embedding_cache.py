"""Precomputed RAG embedding cache loader.

The cache is a JSON file with the shape:

    {
      "model": "sentence-transformers/all-MiniLM-L6-v2",
      "device": "cpu" | "cuda",
      "n_docs": 40,
      "doc_ids": ["from->to", ...],   # optional, used to align with the corpus
      "embeddings": [[...], [...], ...]
    }

It is produced by either:

- ``scripts/brev_embed.py`` (local / Brev GPU)
- ``scripts/sagemaker_processing.py`` (Amazon SageMaker Processing)
- ``scripts/run_pipeline.py`` (single-shot orchestrator)

At runtime the FastAPI app looks for this file (and optionally pulls it
from S3 first) so the cold-start path doesn't have to re-encode every
document on every restart. When the file is missing or stale, the RAG
service silently falls back to live SBERT encoding (or TF-IDF) — the
cache is an *optimisation*, never a hard dependency.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "rag_embeddings.json"
)

# Cache producers may emit a TF-IDF / hash-based fallback when SBERT can't
# be installed inside the SageMaker container. The runtime SBERT encoder
# can't query against those vectors (different space + dim), so we mark
# those models as runtime-incompatible and silently skip them. The artifact
# is still useful as sponsor evidence (`summary.json` records the run).
_RUNTIME_INCOMPATIBLE_MODELS = frozenset(
    {
        "tfidf-sklearn-fallback",
    }
)


@dataclass(frozen=True)
class EmbeddingCache:
    """In-memory representation of a precomputed embedding cache."""

    model: str
    device: str
    n_docs: int
    embeddings: List[List[float]]
    source_path: str
    doc_ids: Optional[List[str]] = None

    @property
    def dim(self) -> int:
        return len(self.embeddings[0]) if self.embeddings else 0

    def matches_corpus_size(self, expected: int) -> bool:
        return self.n_docs == expected and len(self.embeddings) == expected


def _resolve_cache_path() -> Path:
    """Resolve the on-disk cache path.

    Order of precedence:
      1. ``GRIDGREEN_EMBEDDING_CACHE_PATH`` env var
      2. ``backend/data/rag_embeddings.json`` (default)
    """
    env = os.environ.get("GRIDGREEN_EMBEDDING_CACHE_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    return DEFAULT_CACHE_PATH


def _maybe_download_from_s3(target: Path) -> bool:
    """If ``GRIDGREEN_EMBEDDING_CACHE_S3_URI`` is set, mirror it to ``target``.

    Skips the download when ``target`` already exists *and* is newer than
    ``GRIDGREEN_EMBEDDING_CACHE_MAX_AGE_S`` seconds (default 6 hours), so
    the FastAPI worker doesn't hit S3 on every restart.

    Returns ``True`` when the file is present after the call.
    """
    s3_uri = os.environ.get("GRIDGREEN_EMBEDDING_CACHE_S3_URI", "").strip()
    if not s3_uri:
        return target.exists()

    max_age_s = int(os.environ.get("GRIDGREEN_EMBEDDING_CACHE_MAX_AGE_S", "21600"))
    if target.exists():
        try:
            age = max(0.0, _now() - target.stat().st_mtime)
            if age < max_age_s:
                logger.debug(
                    "embedding cache: reusing local mirror %s (age=%.0fs < %ds)",
                    target, age, max_age_s,
                )
                return True
        except OSError:
            pass  # fall through and re-download

    if not s3_uri.startswith("s3://"):
        logger.warning(
            "GRIDGREEN_EMBEDDING_CACHE_S3_URI must start with s3:// (got %r)",
            s3_uri,
        )
        return target.exists()

    try:
        import boto3  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.info("boto3 not installed — cannot pull cache from S3 (%s)", exc)
        return target.exists()

    # s3://bucket/key/path.json
    without_scheme = s3_uri[len("s3://"):]
    if "/" not in without_scheme:
        logger.warning("Malformed S3 URI %r (expected s3://bucket/key)", s3_uri)
        return target.exists()
    bucket, key = without_scheme.split("/", 1)

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        s3 = boto3.client("s3")
        s3.download_file(bucket, key, str(target))
        logger.info("embedding cache: downloaded s3://%s/%s -> %s", bucket, key, target)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding cache: S3 download failed (%s)", exc)
        return target.exists()


def _now() -> float:
    import time

    return time.time()


def load_cache(expected_n_docs: Optional[int] = None) -> Optional[EmbeddingCache]:
    """Best-effort load of the precomputed embedding cache.

    Returns ``None`` (and logs a single info line) when:
      - the cache file does not exist,
      - the JSON is malformed,
      - the cache size doesn't match ``expected_n_docs`` (corpus drift).

    The caller (RAG index) treats ``None`` as "fall back to live encoding".
    """
    if os.environ.get("GRIDGREEN_DISABLE_EMBEDDING_CACHE", "").strip().lower() in {
        "1", "true", "yes",
    }:
        logger.info("embedding cache disabled via GRIDGREEN_DISABLE_EMBEDDING_CACHE")
        return None

    path = _resolve_cache_path()
    _maybe_download_from_s3(path)

    if not path.exists():
        logger.info("embedding cache: no file at %s — using live encoder", path)
        return None

    try:
        raw = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding cache: failed to parse %s (%s)", path, exc)
        return None

    embeddings = raw.get("embeddings") or []
    if not embeddings or not isinstance(embeddings, list):
        logger.warning("embedding cache: %s missing 'embeddings' array", path)
        return None

    cache = EmbeddingCache(
        model=str(raw.get("model", "")),
        device=str(raw.get("device", "")),
        n_docs=int(raw.get("n_docs", len(embeddings))),
        embeddings=embeddings,
        source_path=str(path),
        doc_ids=raw.get("doc_ids"),
    )

    if expected_n_docs is not None and not cache.matches_corpus_size(expected_n_docs):
        logger.warning(
            "embedding cache: size mismatch (cache=%d corpus=%d) — ignoring",
            cache.n_docs, expected_n_docs,
        )
        return None

    if cache.model in _RUNTIME_INCOMPATIBLE_MODELS:
        logger.info(
            "embedding cache: %s is a fallback artifact (model=%s) — runtime will encode live",
            path, cache.model,
        )
        return None

    logger.info(
        "embedding cache: loaded %d docs (dim=%d, model=%s) from %s",
        cache.n_docs, cache.dim, cache.model or "(unknown)", path,
    )
    return cache


def cache_status() -> dict:
    """Lightweight introspection for /api/diagnostics."""
    path = _resolve_cache_path()
    s3 = os.environ.get("GRIDGREEN_EMBEDDING_CACHE_S3_URI", "").strip() or None
    info: dict = {
        "path": str(path),
        "exists": path.exists(),
        "s3_uri": s3,
        "disabled": os.environ.get(
            "GRIDGREEN_DISABLE_EMBEDDING_CACHE", ""
        ).strip().lower() in {"1", "true", "yes"},
    }
    if path.exists():
        try:
            raw = json.loads(path.read_text())
            info["model"] = raw.get("model")
            info["device"] = raw.get("device")
            info["n_docs"] = raw.get("n_docs", len(raw.get("embeddings", [])))
            info["dim"] = len((raw.get("embeddings") or [[]])[0]) if raw.get("embeddings") else 0
            info["size_bytes"] = path.stat().st_size
        except Exception as exc:  # noqa: BLE001
            info["error"] = f"parse: {exc}"
    return info
