# Databricks — bronze table (`gridgreen.raw.eia_raw`)

These files match `scripts/dlt_pipeline.py`, which expects a **Delta** table:

`gridgreen.raw.eia_raw` with columns **`ts_utc`**, **`region_code`**, **`metric`**, **`value`**.

## 1. Catalog + schema + empty table (SQL)

In **Databricks SQL** or a **SQL warehouse**, run:

`01_uc_bootstrap.sql`

(Adjust catalog/schema names if your org forbids `gridgreen`.)

## 2. Seed or load rows (PySpark notebook)

1. **Compute** → cluster with **Spark 3.x** + **Unity Catalog** access.
2. **Workspace** → import `bronze_eia_raw_bootstrap.py` or paste its cells into a notebook.
3. Run **Cell 1** (catalog/schema), **Cell 2** (sample overwrite), or **Cell 3** (append pattern).

First-time load uses **`overwrite`**. Scheduled jobs should use **`append`** (silver DLT dedupes on `ts_utc`, `region_code`, `metric`).

## 3. Optional — load from laptop SQLite via CSV

On your machine (with venv + `ingest_eia` already run):

```bash
cd backend
python -m scripts.export_eia_hourly_to_databricks_csv
```

Upload the generated CSV to **DBFS** or **Volumes**, then use **Cell 4** in the notebook (set `CSV_PATH`).

## 4. Schedule hourly append

**Workflows** → **Jobs** → **Create** → task type **Notebook** / **Python wheel** → pick the append cell logic (or a tiny notebook that only runs the append block with `mode("append")`).

DLT pipeline: still points at `gridgreen.raw.eia_raw` per `dlt_pipeline.py`.
