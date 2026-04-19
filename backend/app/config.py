"""Runtime configuration loaded from env vars."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"
    log_level: str = "INFO"

    eia_api_key: str | None = None

    snowflake_account: str | None = None
    snowflake_user: str | None = None
    snowflake_password: str | None = None
    snowflake_warehouse: str | None = None
    snowflake_database: str = "GRIDGREEN"
    snowflake_schema: str = "PUBLIC"
    snowflake_role: str | None = None

    sqlite_path: str = "backend/data/gridgreen.sqlite"

    cors_allow_origins: str = "http://localhost:3000"

    max_code_bytes: int = 262_144
    default_region: str = "CISO"

    grid_cache_ttl_s: int = 300
    rate_limit_per_minute: int = 60
    request_timeout_s: int = 45

    noaa_token: str | None = None
    gemini_api_key: str | None = None
    wandb_api_key: str | None = None
    wandb_project: str = "gridgreen"

    # Databricks SQL warehouse (optional — set via .env only; never commit real values).
    databricks_server_hostname: str | None = None
    databricks_http_path: str | None = None
    databricks_token: str | None = None
    # Unity Catalog FQN for bronze Delta table (DLT + notebooks read this).
    databricks_bronze_table: str = "gridgreen.raw.eia_raw"
    # Optional Databricks gold/processed table for runtime serving. When set,
    # reads prefer this table before bronze.
    databricks_gold_table: str | None = None
    # Runtime read path for grid endpoints:
    # - local      : SQLite only (default; fastest/stable for dev)
    # - databricks : Databricks SQL only (falls back to SQLite on query/import errors)
    # - auto       : Databricks first when configured, else SQLite
    gridgreen_serve_from: str = "auto"

    # Precomputed RAG embedding cache (built by SageMaker / Brev / run_pipeline).
    # Loaded by `app.services.embedding_cache` at startup.
    gridgreen_embedding_cache_path: str | None = None
    gridgreen_embedding_cache_s3_uri: str | None = None
    gridgreen_embedding_cache_max_age_s: int = 21600  # 6h

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def use_snowflake(self) -> bool:
        return bool(
            self.snowflake_account
            and self.snowflake_user
            and self.snowflake_password
        )

    @property
    def use_databricks_sql(self) -> bool:
        return bool(
            self.databricks_server_hostname
            and self.databricks_http_path
            and self.databricks_token
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def bronze_table_fqn() -> str:
    """Fully qualified bronze table name (cluster `DATABRICKS_BRONZE_TABLE` overrides .env)."""
    env = os.environ.get("DATABRICKS_BRONZE_TABLE")
    if env:
        return env.strip()
    return get_settings().databricks_bronze_table


def databricks_sql_connect_kwargs() -> dict[str, str]:
    """Kwargs compatible with `databricks.sql.connect` / `databricks-sql-connector`."""
    s = get_settings()
    if not s.use_databricks_sql:
        raise RuntimeError(
            "Set databricks_server_hostname, databricks_http_path, and databricks_token"
        )
    return {
        "server_hostname": s.databricks_server_hostname or "",
        "http_path": s.databricks_http_path or "",
        "access_token": s.databricks_token or "",
    }
