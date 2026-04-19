"""Launch an Amazon SageMaker Processing job that builds the RAG embedding cache.

What it does
------------
1. Uploads ``backend/app/data/hf_corpus.json`` to S3 (the job input).
2. Runs ``sagemaker_processing_entry.py`` inside the official scikit-learn
   processing container; the entry script encodes the corpus with
   ``sentence-transformers/all-MiniLM-L6-v2`` (or a TF-IDF fallback) and
   writes ``rag_embeddings.json`` + ``summary.json`` to the output prefix.
3. Optionally waits for the job, then downloads ``rag_embeddings.json``
   to ``backend/data/`` so the FastAPI runtime can pick it up immediately.

This is the **caching** half of the pipeline: SageMaker computes the
expensive document embeddings once and the FastAPI workers consume the
artifact at startup. See ``app/services/embedding_cache.py``.

Prerequisites
-------------
- ``pip install -r backend/requirements-extras.txt`` (adds ``sagemaker``, ``boto3``)
- IAM role whose trust policy allows ``sagemaker.amazonaws.com`` and whose
  permissions allow S3 read/write on your prefixes plus
  ``sagemaker:CreateProcessingJob`` (and ``iam:PassRole``).

Environment (set in ``backend/.env`` or your shell)
---------------------------------------------------
- ``AWS_DEFAULT_REGION``       e.g. ``us-west-2``
- ``SAGEMAKER_ROLE_ARN``       execution role ARN
- ``SAGEMAKER_S3_BUCKET``      bucket for inputs/outputs
- ``SAGEMAKER_S3_PREFIX``      key prefix (default ``gridgreen/sagemaker``)
- ``SAGEMAKER_INSTANCE_TYPE``  default ``ml.t3.medium``

Examples
--------
    cd backend
    source ../.venv/bin/activate

    # Run on SageMaker, wait for completion, download the cache locally:
    python -m scripts.sagemaker_processing --wait --download

    # Just rebuild the cache locally without the round-trip:
    python -m scripts.sagemaker_processing --local
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent
LOCAL_CACHE_PATH = BACKEND_ROOT / "data" / "rag_embeddings.json"


def _load_backend_dotenv() -> None:
    """Load ``backend/.env`` so CLI runs match ``uvicorn`` / tests."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(BACKEND_ROOT / ".env", override=False)


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"Missing required env var: {name}")
    return val


def _build_local() -> int:
    """Run the entry-script logic in-process so people can iterate without AWS."""
    log = logging.getLogger("sagemaker_processing.local")
    log.info("Building embedding cache locally (no SageMaker call).")

    corpus_path = BACKEND_ROOT / "app" / "data" / "hf_corpus.json"
    if not corpus_path.exists():
        raise SystemExit(f"Corpus missing at {corpus_path}")

    # Mirror the SageMaker container layout so the entry script just works.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        in_dir = Path(tmp) / "input" / "data"
        out_dir = Path(tmp) / "output"
        in_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        (in_dir / "hf_corpus.json").write_bytes(corpus_path.read_bytes())

        os.environ["SM_OUTPUT_DATA_DIR"] = str(out_dir)
        # Hot-patch the entry module so its module-level constants point
        # at our temp directories instead of /opt/ml/processing.
        from scripts import sagemaker_processing_entry as entry  # type: ignore

        entry.IN_DIR = in_dir  # type: ignore[attr-defined]
        entry.OUT_DIR = out_dir  # type: ignore[attr-defined]
        entry.main()

        produced = out_dir / "rag_embeddings.json"
        if not produced.exists():
            raise SystemExit("Local build did not produce rag_embeddings.json")
        LOCAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_CACHE_PATH.write_bytes(produced.read_bytes())
        log.info("wrote %s (%d bytes)", LOCAL_CACHE_PATH, LOCAL_CACHE_PATH.stat().st_size)

    return 0


def main(argv: list[str] | None = None) -> int:
    _load_backend_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("sagemaker_processing")

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument(
        "--instance-type",
        default=os.environ.get("SAGEMAKER_INSTANCE_TYPE", "ml.t3.medium"),
        help="SageMaker processing instance type (default ml.t3.medium).",
    )
    p.add_argument(
        "--wait", action="store_true",
        help="Wait for the processing job to finish and print final status.",
    )
    p.add_argument(
        "--download", action="store_true",
        help="After the job succeeds, download rag_embeddings.json to "
             "backend/data/ so FastAPI can pick it up. Implies --wait.",
    )
    p.add_argument(
        "--local", action="store_true",
        help="Build the cache locally (no SageMaker call). Useful for "
             "development or when AWS isn't available.",
    )
    args = p.parse_args(argv)

    if args.local:
        return _build_local()

    try:
        import boto3  # type: ignore
        from sagemaker import Session  # type: ignore
        from sagemaker.processing import ProcessingInput, ProcessingOutput  # type: ignore
        from sagemaker.sklearn.processing import SKLearnProcessor  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            "boto3 / sagemaker are not installed. "
            "Run: pip install -r backend/requirements-extras.txt"
        ) from exc

    region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
    if not region:
        raise SystemExit("Set AWS_DEFAULT_REGION (or AWS_REGION).")

    role = _require("SAGEMAKER_ROLE_ARN")
    bucket = _require("SAGEMAKER_S3_BUCKET")
    prefix = os.environ.get("SAGEMAKER_S3_PREFIX", "gridgreen/sagemaker").strip("/")

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    s3_in = f"{prefix}/runs/{run_id}/input"
    s3_out = f"{prefix}/runs/{run_id}/output"

    corpus_path = BACKEND_ROOT / "app" / "data" / "hf_corpus.json"
    if not corpus_path.exists():
        raise SystemExit(f"Corpus missing at {corpus_path}")

    boto_session = boto3.Session(region_name=region)
    s3 = boto_session.client("s3")
    log.info("Uploading corpus → s3://%s/%s/hf_corpus.json", bucket, s3_in)
    s3.put_object(
        Bucket=bucket,
        Key=f"{s3_in}/hf_corpus.json",
        Body=corpus_path.read_bytes(),
    )

    sm_session = Session(boto_session=boto_session)
    processor = SKLearnProcessor(
        framework_version="1.2-1",
        role=role,
        command=["python3"],
        instance_type=args.instance_type,
        instance_count=1,
        sagemaker_session=sm_session,
    )

    job_name = f"gridgreen-rag-cache-{run_id}".replace("_", "-")[:63]
    log.info("Starting processing job %s (instance=%s)", job_name, args.instance_type)

    entry_script = HERE / "sagemaker_processing_entry.py"
    wait = args.wait or args.download

    processor.run(
        code=str(entry_script),
        inputs=[
            ProcessingInput(
                source=f"s3://{bucket}/{s3_in}/",
                destination="/opt/ml/processing/input/data",
            ),
        ],
        outputs=[
            ProcessingOutput(
                source="/opt/ml/processing/output",
                destination=f"s3://{bucket}/{s3_out}/",
            )
        ],
        job_name=job_name,
        wait=wait,
        logs=wait,
    )

    desc = processor.latest_job.describe()
    status = desc.get("ProcessingJobStatus", "Unknown")
    log.info("processing job status: %s", status)
    print(json.dumps({"job_name": job_name, "status": status}, indent=2))
    artifact_s3 = f"s3://{bucket}/{s3_out}/rag_embeddings.json"
    log.info("artifact: %s", artifact_s3)

    if args.download:
        if status != "Completed":
            log.warning("job did not complete (%s); skipping download", status)
            return 1
        LOCAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading %s → %s", artifact_s3, LOCAL_CACHE_PATH)
        try:
            s3.download_file(
                bucket, f"{s3_out}/rag_embeddings.json", str(LOCAL_CACHE_PATH),
            )
            log.info(
                "saved %s (%d bytes). FastAPI will use it on next restart.",
                LOCAL_CACHE_PATH, LOCAL_CACHE_PATH.stat().st_size,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("download failed (%s)", exc)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
