"""Launch a tiny **Amazon SageMaker Processing** job for the AWS sponsor track.

This is the smallest credible “we used SageMaker” integration for a hackathon:

1. You upload `backend/app/data/hf_corpus.json` to S3 (this script does it).
2. SageMaker runs `sagemaker_processing_entry.py` inside the official
   **scikit-learn** processing container.
3. SageMaker uploads `summary.json` to your S3 output prefix.

Nothing in the FastAPI runtime depends on this — it is an **offline** job
you trigger from a laptop or CI when you want the screenshot / story.

Prereqs
-------
- `pip install -r backend/requirements-extras.txt` (adds `sagemaker`, `boto3`)
- An IAM role whose **trust policy** allows `sagemaker.amazonaws.com` and
  whose **permissions** allow S3 read/write on your chosen prefixes **and**
  `sagemaker:CreateProcessingJob` (+ pass role).

Environment (recommended — set in `backend/.env` or your shell)
----------------------------------------------------------------
- `AWS_DEFAULT_REGION` — e.g. `us-west-2`
- `SAGEMAKER_ROLE_ARN` — execution role ARN for SageMaker
- `SAGEMAKER_S3_BUCKET` — bucket for inputs/outputs
- `SAGEMAKER_S3_PREFIX` — optional key prefix (default `gridgreen/sagemaker`)

Run
---
    cd backend
    source ../.venv/bin/activate
    python -m scripts.sagemaker_processing --instance-type ml.t3.medium
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


def _load_backend_dotenv() -> None:
    """Load `backend/.env` so CLI runs match `uvicorn` / tests without manual `export`."""
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


def _upload_bytes(s3_client, bucket: str, key: str, data: bytes) -> None:
    s3_client.put_object(Bucket=bucket, Key=key, Body=data)


def main(argv: list[str] | None = None) -> int:
    _load_backend_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("sagemaker_processing")

    p = argparse.ArgumentParser()
    p.add_argument(
        "--instance-type",
        default=os.environ.get("SAGEMAKER_INSTANCE_TYPE", "ml.t3.medium"),
        help="SageMaker processing instance type (default ml.t3.medium).",
    )
    p.add_argument(
        "--wait",
        action="store_true",
        help="Wait for the processing job to finish and print final status.",
    )
    args = p.parse_args(argv)

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
    logger.info("Uploading corpus → s3://%s/%s/hf_corpus.json", bucket, s3_in)
    _upload_bytes(s3, bucket, f"{s3_in}/hf_corpus.json", corpus_path.read_bytes())

    sm_session = Session(boto_session=boto_session)

    processor = SKLearnProcessor(
        framework_version="1.2-1",
        role=role,
        command=["python3"],
        instance_type=args.instance_type,
        instance_count=1,
        sagemaker_session=sm_session,
    )

    job_name = f"gridgreen-corpus-{run_id}".replace("_", "-")[:63]
    logger.info("Starting processing job %s", job_name)

    entry_script = HERE / "sagemaker_processing_entry.py"
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
        wait=args.wait,
        logs=True,
    )

    desc = processor.latest_job.describe()
    print(json.dumps({"job_name": job_name, "status": desc["ProcessingJobStatus"]}, indent=2))
    print(
        "Artifacts:",
        f"s3://{bucket}/{s3_out}/",
        "(look for summary.json after SUCCEEDED)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
