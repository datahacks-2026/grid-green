"""Runs *inside* the Amazon SageMaker Processing container.

Purpose: build the **RAG embedding cache** that the FastAPI runtime
loads at startup (``backend/app/services/embedding_cache.py``).

Inputs (mounted by SageMaker):
  ``/opt/ml/processing/input/data/hf_corpus.json``

Outputs (uploaded to ``s3://<bucket>/<prefix>/runs/<id>/output/``):
  ``rag_embeddings.json``  – the cache artifact consumed by the runtime
  ``summary.json``         – small report (n_docs, model, throughput)

The default sklearn processing image does not ship with PyTorch /
sentence-transformers, so we install them on first start. To keep the
job credible even when pip / network is restricted, the script gracefully
falls back to a deterministic TF-IDF vector representation and still
emits a valid ``rag_embeddings.json`` (the runtime treats the cache as
opaque vectors keyed by corpus order).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("sagemaker_entry")


IN_DIR = Path("/opt/ml/processing/input/data")
OUT_DIR = Path(os.environ.get("SM_OUTPUT_DATA_DIR", "/opt/ml/processing/output"))
ST_MODEL = os.environ.get(
    "GRIDGREEN_ST_MODEL", "sentence-transformers/all-MiniLM-L6-v2",
)


def _read_corpus() -> List[dict]:
    json_files = sorted(IN_DIR.glob("*.json"))
    if not json_files:
        raise SystemExit(f"No *.json files under {IN_DIR}")
    data = json.loads(json_files[0].read_text())
    entries = data.get("entries", [])
    if not entries:
        raise SystemExit("Corpus has no entries")
    logger.info("loaded %d corpus entries from %s", len(entries), json_files[0].name)
    return entries


def _doc_text(entry: dict) -> str:
    parts = [
        entry.get("from", ""),
        entry.get("to", ""),
        *(entry.get("tags") or []),
        entry.get("reasoning", ""),
    ]
    return " ".join(p for p in parts if p)


def _doc_id(entry: dict) -> str:
    return f"{entry.get('from', '')}->{entry.get('to', '')}"


def _pip_install(spec: str) -> bool:
    try:
        logger.info("pip install %s", spec)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", spec],
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )
        return True
    except subprocess.CalledProcessError as exc:
        logger.warning("pip install %s failed (%s)", spec, exc)
        return False


def _try_sentence_transformers(
    docs: List[str],
) -> Tuple[str, str, List[List[float]]] | None:
    """Encode with SBERT (preferred). Returns (model, device, embeddings)."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        ok = _pip_install("sentence-transformers")
        if not ok:
            return None
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentence-transformers import still failing (%s)", exc)
            return None

    try:
        import torch  # type: ignore

        device = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        device = "cpu"

    try:
        model = SentenceTransformer(ST_MODEL, device=device)
        t0 = time.perf_counter()
        emb = model.encode(docs, normalize_embeddings=True, show_progress_bar=False)
        elapsed = time.perf_counter() - t0
        logger.info(
            "SBERT encoded %d docs in %.2fs on %s (%.1f docs/s)",
            len(docs), elapsed, device, len(docs) / max(elapsed, 1e-6),
        )
        return ST_MODEL, device, [list(map(float, row)) for row in emb]
    except Exception as exc:  # noqa: BLE001
        logger.warning("SBERT encode failed (%s)", exc)
        return None


def _tfidf_fallback(
    docs: List[str],
) -> Tuple[str, str, List[List[float]]]:
    """sklearn-only fallback: write a low-dim L2-normalised TF-IDF projection.

    The runtime cache loader is dimension-agnostic, so the FastAPI app
    can still consume this artifact (it will simply not match any
    SBERT-encoded query — RAG falls back to TF-IDF for queries when no
    SBERT model is loaded, which is fine since this fallback path is
    only reached when SBERT itself isn't available).
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    vec = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1)
    matrix = vec.fit_transform(docs)
    matrix = normalize(matrix, norm="l2")
    arr = matrix.toarray().tolist()
    logger.info(
        "TF-IDF fallback emitted %d vectors of dim %d", len(arr), len(arr[0]) if arr else 0,
    )
    return "tfidf-sklearn-fallback", "cpu", arr


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = _read_corpus()
    docs = [_doc_text(e) for e in entries]
    doc_ids = [_doc_id(e) for e in entries]

    result = _try_sentence_transformers(docs)
    if result is None:
        logger.warning("Falling back to TF-IDF — install sentence-transformers in the image to use SBERT.")
        model, device, embeddings = _tfidf_fallback(docs)
    else:
        model, device, embeddings = result

    cache = {
        "model": model,
        "device": device,
        "n_docs": len(embeddings),
        "doc_ids": doc_ids,
        "embeddings": embeddings,
    }
    cache_path = OUT_DIR / "rag_embeddings.json"
    cache_path.write_text(json.dumps(cache))
    logger.info(
        "wrote %s (%d docs, dim=%d, model=%s, device=%s)",
        cache_path, cache["n_docs"], len(embeddings[0]) if embeddings else 0, model, device,
    )

    summary = {
        "ok": True,
        "n_entries": len(entries),
        "model": model,
        "device": device,
        "dim": len(embeddings[0]) if embeddings else 0,
        "first_from": entries[0].get("from"),
        "first_to": entries[0].get("to"),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
