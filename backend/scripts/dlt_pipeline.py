"""Databricks Delta Live Tables pipeline for EIA → bronze → silver → gold.

This file is **dual-mode** (a.md §8.10):

1. **Inside Databricks** — when `dlt` is importable, the `@dlt.table`
   decorators register three pipeline stages with the DLT runtime:
     bronze  : raw EIA hourly rows (region, metric, value, ts_utc)
     silver  : cleaned + deduped, parsed timestamps, hourly grain
     gold    : per-region 24h moving-average carbon intensity

2. **Locally** — when `dlt` is missing, the same functions execute in
   pandas against the SQLite store, so you can dry-run the pipeline on
   your laptop and screenshot the output for Devpost. This satisfies
   README §10's "local Python fallback + screenshot" contingency.

Run locally:

    cd backend
    python -m scripts.dlt_pipeline
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

# Allow `python scripts/dlt_pipeline.py` from backend/.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger("dlt_pipeline")


try:  # pragma: no cover — exercised only in Databricks runtime
    import dlt  # type: ignore
    from pyspark.sql import functions as F  # type: ignore

    IN_DATABRICKS = True
except Exception:
    IN_DATABRICKS = False


# ---------------------------------------------------------------------------
# Databricks-native pipeline definitions
# ---------------------------------------------------------------------------

if IN_DATABRICKS:  # pragma: no cover

    @dlt.table(
        name="eia_bronze",
        comment="Raw EIA hourly rows ingested by the FastAPI service.",
    )
    def eia_bronze() -> Any:
        # Replace `eia_raw` with whatever Auto Loader / volume path you wire.
        return spark.readStream.format("delta").table("gridgreen.raw.eia_raw")  # type: ignore

    @dlt.table(name="eia_silver", comment="Deduped + typed.")
    @dlt.expect_or_drop("ts_present", "ts_utc IS NOT NULL")
    @dlt.expect_or_drop("region_present", "region_code IS NOT NULL")
    def eia_silver() -> Any:
        return (
            dlt.read_stream("eia_bronze")
            .dropDuplicates(["ts_utc", "region_code", "metric"])
            .withColumn("ts_utc", F.to_timestamp("ts_utc"))
            .withColumn("value", F.col("value").cast("double"))
        )

    @dlt.table(
        name="eia_gold_carbon_24h_ma",
        comment="24-hour moving avg of carbon intensity per region.",
    )
    def eia_gold() -> Any:
        from pyspark.sql.window import Window  # type: ignore

        w = (
            Window.partitionBy("region_code")
            .orderBy(F.col("ts_utc").cast("long"))
            .rangeBetween(-86400, 0)
        )
        return (
            dlt.read("eia_silver")
            .where(F.col("metric") == "carbon_intensity")
            .withColumn("avg_24h", F.avg("value").over(w))
            .select("region_code", "ts_utc", "value", "avg_24h")
        )


# ---------------------------------------------------------------------------
# Local fallback — same logic in pandas against SQLite
# ---------------------------------------------------------------------------

def run_local() -> None:
    import pandas as pd

    from app.services import storage

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Running DLT-equivalent locally against SQLite (no Databricks).")

    with storage.sqlite_conn() as conn:
        df = pd.read_sql(
            "SELECT ts_utc, region_code, metric, value FROM eia_hourly", conn
        )

    if df.empty:
        logger.warning("No rows in eia_hourly — run scripts.ingest_eia first.")
        return

    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    silver = (
        df.dropna(subset=["ts_utc", "region_code"])
        .drop_duplicates(subset=["ts_utc", "region_code", "metric"])
        .sort_values(["region_code", "ts_utc"])
    )
    logger.info("silver: %d rows after dedup", len(silver))

    carbon = silver[silver["metric"] == "carbon_intensity"].copy()
    if carbon.empty:
        logger.warning("No carbon_intensity rows — gold table is empty.")
        return

    carbon["avg_24h"] = (
        carbon.groupby("region_code")["value"]
        .rolling(window=24, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    summary = carbon.groupby("region_code").agg(
        n_rows=("value", "count"),
        mean_intensity=("value", "mean"),
        mean_24h_ma=("avg_24h", "mean"),
        latest_intensity=("value", "last"),
    )
    print("\n=== gold: eia_gold_carbon_24h_ma (per region) ===")
    print(summary.round(2).to_string())

    # Write back to SQLite as a `gold` table so the same artifact exists locally.
    with storage.sqlite_conn() as conn:
        conn.execute("DROP TABLE IF EXISTS eia_gold_carbon_24h_ma")
        carbon[["region_code", "ts_utc", "value", "avg_24h"]].to_sql(
            "eia_gold_carbon_24h_ma", conn, index=False
        )
        conn.commit()
    logger.info("gold table written to SQLite (eia_gold_carbon_24h_ma)")


if __name__ == "__main__":
    if IN_DATABRICKS:  # pragma: no cover
        # Databricks runs the @dlt.table functions itself; nothing to do here.
        print("Loaded as a DLT pipeline definition.")
    else:
        run_local()
