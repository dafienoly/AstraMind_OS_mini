"""Deterministic, local-only application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LoopbackHost = Literal["127.0.0.1", "localhost", "::1"]


class Settings(BaseSettings):
    """Safe local defaults overridden by .env.local and then process environment."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_prefix="ASTRAMIND_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test"] = "development"
    api_host: LoopbackHost = "127.0.0.1"
    api_port: int = Field(default=8010, ge=1024, le=65535)
    web_port: int = Field(default=5174, ge=1024, le=65535)
    data_dir: Path = Path("var/data")
    control_db_path: Path = Path("var/control/astramind.db")
    rotation_data_dir: Path = Path("var/research/market-rotation")
    market_model_dir: Path = Path("var/research/market-models")
    tushare_token: SecretStr | None = None
    tushare_api_url: str = "https://api.tushare.pro"
    tushare_rate_limit_per_minute: int = Field(default=120, ge=1, le=500)
    tushare_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    tushare_max_retries: int = Field(default=2, ge=0, le=5)
    miniqmt_python: str | None = None
    miniqmt_xtquant_path: Path | None = None
    miniqmt_quote_port: int | None = Field(default=None, ge=1024, le=65535)
    miniqmt_probe_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    miniqmt_fresh_tick_wait_seconds: float = Field(default=8.0, ge=0, le=30)
    miniqmt_account_id: SecretStr | None = None
    miniqmt_account_mode: Literal["simulation", "live"] | None = None
    miniqmt_userdata_path: SecretStr | None = None
    miniqmt_account_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    miniqmt_callback_wait_seconds: float = Field(default=2.0, ge=0, le=10)
    account_reconciliation_dir: Path = Path("var/control/account-reconciliation")
    shadow_db_path: Path = Path("var/control/shadow.sqlite3")
    backup_dir: Path | None = None
    recovery_drill_dir: Path = Path("var/recovery-drills")
    local_ops_db_path: Path = Path("var/control/local-ops.sqlite3")

    @field_validator(
        "tushare_token",
        "miniqmt_account_id",
        "miniqmt_userdata_path",
        mode="before",
    )
    @classmethod
    def empty_secret_is_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("backup_dir", mode="before")
    @classmethod
    def empty_path_is_none(cls, value: object) -> object:
        return None if value == "" else value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
