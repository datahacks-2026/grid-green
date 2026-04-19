"""GridGreen end-to-end pipeline — one command, four stages.

This is the unified entry point that ties the data + model + cache +
warehouse layers together so a fresh checkout can go from "no data" to
"FastAPI ready to serve" with a single command.

Stages
------
1. **Ingest grid data** — pulls EIA hourly carbon-intensity into
   ``backend/data/gridgreen.sqlite`` (mock series when ``EIA_API_KEY``
   is unset). Snowflake mirroring fires automatically when the
   ``SNOWFLAKE_*`` env is configured (see ``app/services/storage.py``).
2. **Build the RAG embedding cache** — encodes ``hf_corpus.json`` once
   and writes ``backend/data/rag_embeddings.json``. Choose where the
   compute happens:
       --cache=local      use the in-process encoder (default, fast for dev)
       --cache=sagemaker  offload to Amazon SageMaker Processing (cloud)
       --cache=skip       leave the existing cache file untouched
3. **Databricks bronze refresh** — export the freshly-ingested
   ``eia_hourly`` rows to CSV and (when ``DATABRICKS_SERVER_HOSTNAME`` +
   ``DATABRICKS_TOKEN`` are set) upload via the **Files API** to a UC
   volume path (``/Volumes/...``) or legacy **DBFS**, trying several
   candidates until one succeeds. Also runs
   the in-pandas DLT-equivalent against SQLite so the gold
   ``eia_gold_carbon_24h_ma`` materialised view exists locally.
       --databricks=auto    (default) upload when configured, else local-only
       --databricks=local   only run the pandas DLT fallback (no DBFS upload)
       --databricks=upload  require Databricks env, fail if missing
       --databricks=skip    don't touch CSV / DBFS / local DLT
4. **Diagnose** — print a one-screen readiness report (matches the
   ``GET /api/diagnostics`` endpoint shape) so you can confirm what the
   API will see before you start the server.

Examples
--------
    cd backend
    source ../.venv/bin/activate

    # Full pipeline, all defaults
    #   ingest 30d → local cache build → CSV+DLT (DBFS upload if configured) → report
    python -m scripts.run_pipeline

    # Cloud cache build (waits for SageMaker, then mirrors artifact locally)
    python -m scripts.run_pipeline --cache sagemaker

    # Refresh just the embedding cache without re-ingesting / touching DBFS
    python -m scripts.run_pipeline --skip-ingest --databricks skip

    # Pipeline-only, no embedding work, but still refresh the warehouse layer
    python -m scripts.run_pipeline --cache skip
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger("run_pipeline")


def _format_exc_for_summary(exc: BaseException, max_len: int = 420) -> str:
    """Single-line, length-capped message for pipeline summary (incl. __cause__)."""
    parts: List[str] = []
    chain: BaseException | None = exc
    depth = 0
    while chain is not None and depth < 4:
        bit = str(chain).strip()
        if bit:
            parts.append(f"{type(chain).__name__}: {bit}")
        else:
            parts.append(type(chain).__name__)
        chain = chain.__cause__
        depth += 1
    msg = " | ".join(parts) if parts else repr(exc)
    msg = msg.replace("\n", " ").strip()
    while "  " in msg:
        msg = msg.replace("  ", " ")
    if len(msg) > max_len:
        return msg[: max_len - 3] + "..."
    return msg


@dataclass
class StageResult:
    name: str
    ok: bool
    detail: str
    elapsed_s: float


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    load_dotenv(ROOT / ".env", override=False)


def _run_stage(name: str, fn: Callable[[], str]) -> StageResult:
    logger.info("── stage: %s ──", name)
    t0 = time.perf_counter()
    try:
        detail = fn() or "ok"
        return StageResult(name, True, detail, time.perf_counter() - t0)
    except SystemExit as exc:
        return StageResult(name, False, f"SystemExit: {exc}", time.perf_counter() - t0)
    except Exception as exc:  # noqa: BLE001
        logger.exception("stage %s failed", name)
        return StageResult(
            name, False, f"{type(exc).__name__}: {exc}", time.perf_counter() - t0,
        )


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def _stage_ingest(days: int, region: str | None) -> str:
    from scripts import ingest_eia  # local import to avoid pulling deps when skipped

    argv: List[str] = ["--days", str(days)]
    if region:
        argv += ["--region", region]
    rc = ingest_eia.main(argv)
    if rc != 0:
        raise RuntimeError(f"ingest_eia exited {rc}")
    from app.config import get_settings

    snow = " (also mirrored to Snowflake)" if get_settings().use_snowflake else ""
    return f"ingested last {days}d for {region or 'all regions'}{snow}"


def _stage_build_cache_local() -> str:
    from scripts import sagemaker_processing as sm

    rc = sm._build_local()  # noqa: SLF001 — internal helper exposed for the pipeline
    if rc != 0:
        raise RuntimeError(f"local cache build exited {rc}")
    cache_path = ROOT / "data" / "rag_embeddings.json"
    return f"wrote {cache_path} ({cache_path.stat().st_size} bytes)"


def _stage_build_cache_sagemaker(instance_type: str | None, wait: bool) -> str:
    from scripts import sagemaker_processing as sm

    argv: List[str] = ["--download"]
    if not wait:
        # --download already implies wait, but keep the flag explicit.
        pass
    if instance_type:
        argv += ["--instance-type", instance_type]
    rc = sm.main(argv)
    if rc != 0:
        raise RuntimeError(f"SageMaker pipeline exited {rc}")
    cache_path = ROOT / "data" / "rag_embeddings.json"
    if not cache_path.exists():
        raise RuntimeError("SageMaker job ran but rag_embeddings.json was not downloaded")
    return f"downloaded {cache_path} ({cache_path.stat().st_size} bytes)"


def _stage_databricks(mode: str) -> str:
    """Refresh the warehouse layer.

    1. Export ``eia_hourly`` rows to ``backend/data/exports/eia_hourly_export.csv``.
    2. When hostname + PAT are set, upload the CSV (UC ``/Volumes/...`` via
       Files API, then DBFS fallbacks — see ``upload_eia_export_to_databricks``).
    3. Run the DLT-equivalent in pandas (``dlt_pipeline.run_local``) so the
       SQLite store gets the gold ``eia_gold_carbon_24h_ma`` table even when
       no Databricks workspace is wired up.
    """
    from app.config import get_settings

    summary_parts: List[str] = []

    # 1) Always export — cheap, and the artifact is the contract with the bronze notebook.
    from scripts import export_eia_hourly_to_databricks_csv as exp

    rc = exp.main()
    if rc != 0:
        raise RuntimeError(f"CSV export exited {rc}")
    csv_path = Path(ROOT) / "data" / "exports" / "eia_hourly_export.csv"
    if csv_path.exists():
        summary_parts.append(f"csv={csv_path.name} ({csv_path.stat().st_size}B)")

    # 2) Workspace upload (Files API for /Volumes/..., else DBFS). Only needs
    # hostname + PAT; SQL warehouse HTTP path is *not* required for this step.
    settings = get_settings()
    workspace_ready = bool(
        settings.databricks_server_hostname and settings.databricks_token
    )
    if mode in {"auto", "upload"} and workspace_ready:
        try:
            from scripts.upload_eia_export_to_databricks import upload_export_file

            remote = upload_export_file(str(csv_path))
            summary_parts.append(f"uploaded→{remote}")
        except Exception as exc:  # noqa: BLE001
            if mode == "upload":
                raise
            logger.warning(
                "Databricks upload failed; continuing with local DLT fallback: %s",
                exc,
                exc_info=True,
            )
            detail = _format_exc_for_summary(exc)
            print(
                "\n======== Databricks upload failed (CSV is still local) ========\n"
                f"{detail}\n"
                "Fix: set DATABRICKS_UC_VOLUME_EXPORT_PATH, DATABRICKS_VOLUME_NAME, or "
                "DATABRICKS_WORKSPACE_EXPORT_PATH — or rely on local DLT only (--databricks local).\n"
                "================================================================\n",
                file=sys.stderr,
            )
            summary_parts.append(
                f"upload skipped ({type(exc).__name__}): {detail}"
            )
    elif mode == "upload":
        raise RuntimeError(
            "DATABRICKS_SERVER_HOSTNAME and DATABRICKS_TOKEN must be set for --databricks=upload"
        )
    else:
        summary_parts.append("workspace upload skipped")

    # 3) Local DLT fallback — bronze→silver→gold in pandas, writes
    # `eia_gold_carbon_24h_ma` to SQLite. Cheap and deterministic.
    try:
        from scripts import dlt_pipeline

        dlt_pipeline.run_local()
        summary_parts.append("local DLT (gold table) refreshed")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Local DLT fallback failed (%s)", exc)
        summary_parts.append(f"local DLT failed ({type(exc).__name__})")

    return "; ".join(summary_parts) or "ok"


def _stage_diagnose() -> str:
    """Print a compact readiness summary mirroring /api/diagnostics."""
    from app.config import get_settings
    from app.services import embedding_cache as ec

    lines: List[str] = []

    sqlite_path = Path(get_settings().sqlite_path)
    if sqlite_path.exists():
        lines.append(f"  sqlite       : {sqlite_path} ({sqlite_path.stat().st_size} bytes)")
    else:
        lines.append(f"  sqlite       : MISSING ({sqlite_path}) — run ingest first")

    # Embedding cache
    status = ec.cache_status()
    if status.get("exists"):
        lines.append(
            f"  rag cache    : {status['path']} "
            f"(model={status.get('model')}, n_docs={status.get('n_docs')}, dim={status.get('dim')})"
        )
    else:
        lines.append(f"  rag cache    : MISSING ({status['path']}) — RAG will encode on first request")
    if status.get("s3_uri"):
        lines.append(f"  rag cache s3 : {status['s3_uri']}")

    csv_path = Path(ROOT) / "data" / "exports" / "eia_hourly_export.csv"
    if csv_path.exists():
        lines.append(
            f"  databricks   : csv ready at {csv_path} ({csv_path.stat().st_size} bytes)"
        )
    else:
        lines.append(f"  databricks   : no CSV export yet ({csv_path})")

    s = get_settings()
    flags = [
        ("snowflake", s.use_snowflake),
        ("databricks_sql", s.use_databricks_sql),
        ("eia_api_key", bool(s.eia_api_key)),
        ("noaa_token", bool(s.noaa_token)),
        ("gemini_api_key", bool(s.gemini_api_key)),
        ("wandb_api_key", bool(s.wandb_api_key)),
    ]
    flag_str = ", ".join(f"{k}={'on' if v else 'off'}" for k, v in flags)
    lines.append(f"  integrations : {flag_str}")

    print("\nReadiness report")
    print("================")
    for ln in lines:
        print(ln)
    print("\nNext step: uvicorn app.main:app --reload\n")
    return "diagnostics printed"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--skip-ingest", action="store_true", help="Don't refresh EIA data.")
    p.add_argument("--days", type=int, default=int(os.environ.get("PIPELINE_DAYS", "30")))
    p.add_argument("--region", default=None, help="Restrict ingest to one region.")
    p.add_argument(
        "--cache",
        choices=["local", "sagemaker", "skip"],
        default=os.environ.get("PIPELINE_CACHE", "local"),
        help="Where to build the RAG embedding cache (default: local).",
    )
    p.add_argument(
        "--instance-type",
        default=None,
        help="SageMaker processing instance type (only used when --cache=sagemaker).",
    )
    p.add_argument(
        "--databricks",
        choices=["auto", "local", "upload", "skip"],
        default=os.environ.get("PIPELINE_DATABRICKS", "auto"),
        help=(
            "Warehouse-layer behavior (default: auto).\n"
            "  auto   → CSV + DLT-local; DBFS upload only if DATABRICKS_* configured\n"
            "  local  → CSV + DLT-local only (no DBFS upload)\n"
            "  upload → CSV + DBFS upload + DLT-local; fail if DATABRICKS_* missing\n"
            "  skip   → don't touch CSV / DBFS / local DLT"
        ),
    )
    args = p.parse_args(argv)

    results: List[StageResult] = []

    if args.skip_ingest:
        logger.info("── stage: ingest (skipped via --skip-ingest) ──")
    else:
        results.append(_run_stage("ingest_eia", lambda: _stage_ingest(args.days, args.region)))

    if args.cache == "skip":
        logger.info("── stage: build cache (skipped via --cache=skip) ──")
    elif args.cache == "local":
        results.append(_run_stage("build_cache_local", _stage_build_cache_local))
    else:  # sagemaker
        results.append(
            _run_stage(
                "build_cache_sagemaker",
                lambda: _stage_build_cache_sagemaker(args.instance_type, wait=True),
            )
        )

    if args.databricks == "skip":
        logger.info("── stage: databricks (skipped via --databricks=skip) ──")
    else:
        results.append(
            _run_stage("databricks", lambda: _stage_databricks(args.databricks))
        )

    results.append(_run_stage("diagnose", _stage_diagnose))

    print("\nPipeline summary")
    print("================")
    failed = 0
    for r in results:
        flag = "OK " if r.ok else "FAIL"
        print(f"  [{flag}] {r.name:<24} {r.elapsed_s:6.2f}s  {r.detail}")
        if not r.ok:
            failed += 1
    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
