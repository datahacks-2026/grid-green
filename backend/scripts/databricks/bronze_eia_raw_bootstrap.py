# Databricks notebook source
# MAGIC %md
# MAGIC # GridGreen — create / seed `gridgreen.raw.eia_raw` (bronze)
# MAGIC
# MAGIC Prerequisites: cluster with Spark 3.x + Delta + **Unity Catalog** permission on `gridgreen`.
# MAGIC
# MAGIC Column contract (must match `scripts/dlt_pipeline.py` silver expectations):
# MAGIC - `ts_utc`, `region_code`, `metric`, `value`

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE CATALOG IF NOT EXISTS gridgreen;
# MAGIC CREATE SCHEMA IF NOT EXISTS gridgreen.raw;

# COMMAND ----------

import os

from datetime import datetime, timezone

from pyspark.sql import types as T

BRONZE_TABLE = os.environ.get("DATABRICKS_BRONZE_TABLE", "gridgreen.raw.eia_raw")

schema = T.StructType(
    [
        T.StructField("ts_utc", T.TimestampType(), False),
        T.StructField("region_code", T.StringType(), False),
        T.StructField("metric", T.StringType(), False),
        T.StructField("value", T.DoubleType(), False),
    ]
)

# Use real datetime objects — TimestampType + string tuples breaks Arrow conversion
# (assert isinstance(value, datetime.datetime)).
def utc(*, y: int, m: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, 0, tzinfo=timezone.utc)


sample_rows = [
    (utc(y=2026, m=4, d=18, h=12), "CISO", "carbon_intensity", 450.0),
    (utc(y=2026, m=4, d=18, h=13), "CISO", "carbon_intensity", 448.5),
    (utc(y=2026, m=4, d=18, h=12), "PJM", "carbon_intensity", 410.0),
]

df = spark.createDataFrame(sample_rows, schema)

(
    df.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(BRONZE_TABLE)
)

display(spark.table(BRONZE_TABLE).orderBy("region_code", "ts_utc"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Scheduled append (hourly job)
# MAGIC
# MAGIC Use **`append`** after the initial **`overwrite`**. Silver DLT dedupes on
# MAGIC `(ts_utc, region_code, metric)`.

# COMMAND ----------

import os

from datetime import datetime, timezone

from pyspark.sql import types as T

BRONZE_TABLE = os.environ.get("DATABRICKS_BRONZE_TABLE", "gridgreen.raw.eia_raw")

schema = T.StructType(
    [
        T.StructField("ts_utc", T.TimestampType(), False),
        T.StructField("region_code", T.StringType(), False),
        T.StructField("metric", T.StringType(), False),
        T.StructField("value", T.DoubleType(), False),
    ]
)

# Example: one new hour for CISO — replace with your EIA pull / transform.
now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
rows = [(now, "CISO", "carbon_intensity", 445.0)]

df = spark.createDataFrame(rows, schema)

df.write.format("delta").mode("append").saveAsTable(BRONZE_TABLE)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Optional — load from CSV (exported from laptop SQLite)
# MAGIC
# MAGIC 1. Run locally: `python -m scripts.export_eia_hourly_to_databricks_csv`
# MAGIC 2. Upload `eia_hourly_export.csv` to **Volumes** or **DBFS**.
# MAGIC 3. Set `CSV_PATH` below.

# COMMAND ----------

# CSV_PATH = "/Volumes/gridgreen/raw/landing/eia_hourly_export.csv"
# CSV_PATH = "dbfs:/FileStore/gridgreen/eia_hourly_export.csv"

# df_csv = (
#     spark.read.option("header", True)
#     .option("inferSchema", True)
#     .csv(CSV_PATH)
# )
# # Expect columns: ts_utc, region_code, metric, value (match SQLite export script).
# df_csv = (
#     df_csv.withColumn("ts_utc", F.to_timestamp(F.col("ts_utc")))
#     .select("ts_utc", "region_code", "metric", "value")
# )
# df_csv.write.format("delta").mode("overwrite").saveAsTable(BRONZE_TABLE)
