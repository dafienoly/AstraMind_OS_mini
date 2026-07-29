from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from astramind_mini.data.adapters.provider_config import TushareProbeConfig
from astramind_mini.data.adapters.tushare_client import (
    TushareHttpClient,
    TushareRequestError,
)


def _config() -> TushareProbeConfig:
    placeholder = SecretStr("synthetic-test-value")
    return TushareProbeConfig(
        api_url="https://provider.example/api",
        token=placeholder,
        rate_limit_per_minute=500,
        timeout_seconds=1,
        max_retries=2,
    )


def test_generic_provider_error_is_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(200, json={"code": -1, "msg": "temporary error"})
        return httpx.Response(
            200,
            json={"code": 0, "data": {"fields": ["value"], "items": [[1]]}},
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await TushareHttpClient(_config(), client).query(
                "sample",
                params={},
                fields=("value",),
            )
            assert result.rows == ({"value": 1},)

    asyncio.run(exercise())
    assert attempts == 2


def test_permission_error_fails_without_retry() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json={"code": -1, "msg": "permission denied"})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(TushareRequestError, match="permission_denied"):
                await TushareHttpClient(_config(), client).query(
                    "sample",
                    params={},
                    fields=("value",),
                )

    asyncio.run(exercise())
    assert attempts == 1
