# Cloud Integration Setup

How to configure each cloud service GridGreen integrates with. All env vars go in `backend/.env` (copy from `backend/.env.example`).

Every integration is **optional** — the app runs fully offline with SQLite and mock EIA data.

---

## EIA (US Energy Information Administration)

**What it does:** Provides real hourly grid carbon intensity for 5 US regions.

**Setup:**
1. Get a free API key at https://www.eia.gov/opendata/
2. Set in `backend/.env`:
   ```
   EIA_API_KEY=your_key_here
   ```
3. Run the ingest:
   ```bash
   cd backend
   python -m scripts.ingest_eia
   ```
4. Verify:
   ```bash
   curl -s http://127.0.0.1:8000/api/diagnostics | python3 -m json.tool
   # Check storage.eia_hourly.row_count > 0
   ```

**Without it:** A deterministic mock series is used so the app works offline.

---

## Snowflake

**What it does:** Cortex vector search for RAG model suggestions; EIA data mirror.

**Setup:**
1. Create a Snowflake account (trial works)
2. Run the setup SQL in your Snowflake worksheet:
   ```sql
   CREATE DATABASE IF NOT EXISTS GRIDGREEN;
   USE DATABASE GRIDGREEN;
   CREATE SCHEMA IF NOT EXISTS PUBLIC;
   CREATE WAREHOUSE IF NOT EXISTS GRIDGREEN_WH
     WITH WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60;
   CREATE ROLE IF NOT EXISTS GRIDGREEN_ROLE;
   GRANT USAGE ON DATABASE GRIDGREEN TO ROLE GRIDGREEN_ROLE;
   GRANT USAGE ON SCHEMA GRIDGREEN.PUBLIC TO ROLE GRIDGREEN_ROLE;
   GRANT CREATE TABLE ON SCHEMA GRIDGREEN.PUBLIC TO ROLE GRIDGREEN_ROLE;
   GRANT USAGE ON WAREHOUSE GRIDGREEN_WH TO ROLE GRIDGREEN_ROLE;
   CREATE USER IF NOT EXISTS GRIDGREEN_USER
     PASSWORD = 'YourPassword'
     DEFAULT_ROLE = GRIDGREEN_ROLE
     DEFAULT_WAREHOUSE = GRIDGREEN_WH;
   GRANT ROLE GRIDGREEN_ROLE TO USER GRIDGREEN_USER;
   ```
3. Set in `backend/.env`:
   ```
   SNOWFLAKE_ACCOUNT=your_account_id
   SNOWFLAKE_USER=GRIDGREEN_USER
   SNOWFLAKE_PASSWORD=YourPassword
   SNOWFLAKE_WAREHOUSE=GRIDGREEN_WH
   SNOWFLAKE_DATABASE=GRIDGREEN
   SNOWFLAKE_SCHEMA=PUBLIC
   SNOWFLAKE_ROLE=GRIDGREEN_ROLE
   ```
4. Install the package:
   ```bash
   pip install snowflake-connector-python
   ```
5. Build the RAG index in Snowflake:
   ```bash
   cd backend
   python -m scripts.build_rag_index --target snowflake
   ```
6. Verify at `/api/diagnostics` — `integrations.snowflake.configured` should be `true`.

**Without it:** RAG runs locally with TF-IDF or Sentence-Transformers. No Snowflake needed.

---

## Databricks

**What it does:** Delta Live Tables pipeline for EIA data ingestion and feature engineering.

**Setup:**
1. Create a Databricks workspace (Community Edition or trial)
2. Create a SQL warehouse and get the connection details
3. Install packages:
   ```bash
   pip install databricks-sql-connector databricks-sdk
   ```
4. Set in `backend/.env`:
   ```
   DATABRICKS_SERVER_HOSTNAME=adb-1234567890.12.azuredatabricks.net
   DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/your_warehouse_id
   DATABRICKS_TOKEN=<your_databricks_token_placeholder>
   DATABRICKS_BRONZE_TABLE=gridgreen.raw.eia_raw
   ```
5. Run the DLT pipeline:
   ```bash
   cd backend
   python -m scripts.dlt_pipeline
   ```
   This runs in **dual mode**: inside Databricks it registers `@dlt.table` stages; locally it falls back to pandas + SQLite.

6. Optionally upload EIA data to Databricks:
   ```bash
   python -m scripts.upload_eia_export_to_databricks
   ```

**Without it:** The DLT script runs locally with pandas + SQLite. For the Databricks prize, you need an actual pipeline run inside a Databricks workspace.

---

## AWS SageMaker

**What it does:** Runs a SageMaker Processing Job for embedding generation.

**Setup:**
1. Configure AWS credentials (either `aws configure` or env vars):
   ```
   AWS_ACCESS_KEY_ID=your_key
   AWS_SECRET_ACCESS_KEY=your_secret
   AWS_DEFAULT_REGION=us-east-1
   ```
2. Create an IAM role for SageMaker with `AmazonSageMakerFullAccess` and set:
   ```
   SAGEMAKER_ROLE_ARN=arn:aws:iam::123456789012:role/your-sagemaker-role
   SAGEMAKER_S3_BUCKET=your-bucket-name
   SAGEMAKER_S3_PREFIX=gridgreen/sagemaker
   SAGEMAKER_INSTANCE_TYPE=ml.t3.medium
   ```
3. Install boto3 (usually already installed):
   ```bash
   pip install boto3 sagemaker
   ```
4. Run:
   ```bash
   cd backend
   python -m scripts.sagemaker_processing
   ```
5. Capture the job ARN and console screenshot for Devpost.

**Without it:** Embeddings are generated locally. SageMaker is for the AWS prize.

---

## NVIDIA Brev

**What it does:** Runs the embedding workload on a GPU instance.

**Setup:**
1. Sign up at https://brev.dev and provision a GPU instance
2. SSH into your Brev instance
3. Clone the repo and install dependencies:
   ```bash
   git clone <repo-url>
   cd green-watts
   pip install -r backend/requirements.txt
   pip install -r backend/requirements-extras.txt
   ```
4. Run the embedding workload:
   ```bash
   cd backend
   python -m scripts.brev_embed
   ```
   This encodes the RAG corpus on GPU and saves the artifact.

5. Optionally log to W&B (see below):
   ```bash
   WANDB_API_KEY=your_key python -m scripts.brev_embed
   ```

**Without it:** Embeddings run on CPU locally. Brev is for the NVIDIA prize.

---

## Weights & Biases (W&B)

**What it does:** Logs embedding workload metrics (used with Brev script).

**Setup:**
1. Sign up at https://wandb.ai and get your API key
2. Set in `backend/.env`:
   ```
   WANDB_API_KEY=your_key_here
   WANDB_PROJECT=gridgreen
   ```
3. The Brev embedding script (`python -m scripts.brev_embed`) automatically logs to W&B when the key is set.

**Without it:** The script runs without logging. W&B is optional observability.

---

## Google Gemini

**What it does:** Polishes RAG suggestion reasoning into natural-language paragraphs.

**Setup:**
1. Get an API key at https://aistudio.google.com/apikey
2. Install the package:
   ```bash
   pip install google-generativeai
   ```
3. Set in `backend/.env`:
   ```
   GEMINI_API_KEY=your_key_here
   ```
4. Restart the backend — Gemini polish activates automatically for both HTTP and MCP paths.

**Without it:** Raw RAG reasoning passes through unchanged. The app works identically; Gemini only affects text formatting.

---

## Quick Status Check

Run the diagnostics endpoint to see what's configured:

```bash
curl -s http://127.0.0.1:8000/api/diagnostics | python3 -m json.tool
```

Look at the `integrations` block — each service shows `configured: true/false` and `package_installed: true/false`.
