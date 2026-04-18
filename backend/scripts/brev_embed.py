"""Reference Brev.dev embedding workload (a.md §8.8 + sponsor evidence).

Designed to be the *single* GPU-touching script in the project. Run it
once on a Brev instance to:

1. Encode the curated HF corpus with `sentence-transformers/all-MiniLM-L6-v2`
   on a GPU (this is the NVIDIA challenge proof).
2. Log the run + a small loss / throughput chart to **Weights & Biases**
   (the W&B challenge proof — set `WANDB_API_KEY`).
3. Emit a JSON file (`backend/data/rag_embeddings.json`) that the runtime
   RAG service will load instead of recomputing on first request.

Local CPU also works — the GPU path is `device='cuda'` if available, and
the script prints whether it ran on GPU so you can screenshot it.

Run on Brev:

    pip install -r requirements.txt -r requirements-extras.txt
    python -m scripts.brev_embed
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.services import rag  # noqa: E402

logger = logging.getLogger("brev_embed")

OUT_PATH = Path(ROOT) / "data" / "rag_embeddings.json"


def _maybe_wandb() -> Any:
    try:
        import wandb  # type: ignore

        if not os.environ.get("WANDB_API_KEY"):
            logger.info("WANDB_API_KEY not set — skipping W&B logging.")
            return None
        run = wandb.init(
            project=os.environ.get("WANDB_PROJECT", "gridgreen"),
            name="brev-embed",
            config={"model": "sentence-transformers/all-MiniLM-L6-v2"},
        )
        return run
    except Exception as exc:  # noqa: BLE001
        logger.info("W&B unavailable (%s) — skipping", exc)
        return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception:
        logger.error(
            "sentence-transformers not installed. Install requirements-extras.txt first."
        )
        return 1

    try:
        import torch  # type: ignore
        device = "cuda" if torch.cuda.is_available() else "cpu"
        gpu_name = torch.cuda.get_device_name(0) if device == "cuda" else "(cpu)"
    except Exception:
        device = "cpu"
        gpu_name = "(cpu)"

    logger.info("device=%s gpu=%s", device, gpu_name)

    index = rag.get_index()
    index._ensure_loaded()  # noqa: SLF001 — internal access for the script
    docs = [e.doc_text for e in index._entries]  # noqa: SLF001
    n_docs = len(docs)

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device=device)
    t0 = time.perf_counter()
    embeddings = model.encode(docs, normalize_embeddings=True, show_progress_bar=True)
    elapsed = time.perf_counter() - t0
    throughput = n_docs / elapsed if elapsed else 0.0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "model": "sentence-transformers/all-MiniLM-L6-v2",
                "device": device,
                "gpu_name": gpu_name,
                "n_docs": n_docs,
                "elapsed_s": round(elapsed, 3),
                "throughput_docs_per_s": round(throughput, 2),
                "embeddings": [emb.tolist() for emb in embeddings],
            },
            indent=2,
        )
    )
    logger.info(
        "wrote %s (%d docs, %.2f docs/s on %s)",
        OUT_PATH, n_docs, throughput, gpu_name,
    )

    run = _maybe_wandb()
    if run is not None:
        run.log({
            "n_docs": n_docs,
            "elapsed_s": elapsed,
            "throughput_docs_per_s": throughput,
            "device": device,
        })
        run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
