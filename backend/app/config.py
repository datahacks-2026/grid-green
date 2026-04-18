"""Runtime configuration loaded from env vars."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
