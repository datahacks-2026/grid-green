-- Unity Catalog bootstrap for GridGreen bronze (raw EIA-style rows).
-- Run in: Databricks SQL editor / SQL warehouse.
-- Aligns with: backend/scripts/dlt_pipeline.py → gridgreen.raw.eia_raw

CREATE CATALOG IF NOT EXISTS gridgreen;
CREATE SCHEMA IF NOT EXISTS gridgreen.raw;

-- Managed Delta table (empty OK — notebook job will append/overwrite).
CREATE TABLE IF NOT EXISTS gridgreen.raw.eia_raw (
  ts_utc TIMESTAMP,
  region_code STRING,
  metric STRING,
  value DOUBLE
)
USING DELTA
COMMENT 'Bronze: hourly EIA-style points (carbon_intensity gCO2/kWh per BA).';

-- Sanity check
-- SELECT * FROM gridgreen.raw.eia_raw LIMIT 10;
