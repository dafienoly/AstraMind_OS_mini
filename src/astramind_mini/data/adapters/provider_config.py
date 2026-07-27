"""Allowlisted provider configuration with explicit source precedence."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from astramind_mini.config import Settings

KEYS: Final = {
    "TUSHARE_API_URL": "api_url",
    "ASTRAMIND_TUSHARE_API_URL": "api_url",
    "TUSHARE_TOKEN": "token",
    "ASTRAMIND_TUSHARE_TOKEN": "token",
    "ASTRAMIND_TUSHARE_RATE_LIMIT_PER_MINUTE": "rate_limit_per_minute",
    "ASTRAMIND_TUSHARE_TIMEOUT_SECONDS": "timeout_seconds",
    "ASTRAMIND_TUSHARE_MAX_RETRIES": "max_retries",
}


class TushareProbeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_url: str
    token: SecretStr
    rate_limit_per_minute: int = Field(ge=1, le=500)
    timeout_seconds: float = Field(gt=0, le=120)
    max_retries: int = Field(ge=0, le=5)


def load_tushare_probe_config(
    settings: Settings,
    provider_env_file: Path,
    local_env_file: Path = Path(".env.local"),
) -> TushareProbeConfig:
    if not provider_env_file.is_file():
        raise FileNotFoundError(f"提供方配置文件不存在：{provider_env_file}")
    values: dict[str, object] = {
        "api_url": settings.tushare_api_url,
        "token": settings.tushare_token.get_secret_value() if settings.tushare_token else "",
        "rate_limit_per_minute": settings.tushare_rate_limit_per_minute,
        "timeout_seconds": settings.tushare_timeout_seconds,
        "max_retries": settings.tushare_max_retries,
    }
    _apply(values, dotenv_values(provider_env_file))
    if local_env_file.is_file():
        _apply(values, dotenv_values(local_env_file))
    _apply(values, os.environ)
    credential = str(values["token"])
    if not credential:
        raise ValueError("Tushare Token 未配置")
    return TushareProbeConfig.model_validate(values)


def _apply(target: dict[str, object], source: Mapping[str, object]) -> None:
    for key, value in source.items():
        field = KEYS.get(str(key))
        if field and value not in {None, ""}:
            target[field] = value


__all__ = ["TushareProbeConfig", "load_tushare_probe_config"]
