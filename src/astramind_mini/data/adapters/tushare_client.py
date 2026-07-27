"""Reusable Tushare-compatible HTTP client for production Data ingestion."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from time import monotonic

import httpx

from ..application.identity import content_hash
from ..ports import ProviderTable
from .provider_config import TushareProbeConfig


class TushareRequestError(RuntimeError):
    def __init__(self, code: str, *, recoverable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.recoverable = recoverable


class TushareHttpClient:
    def __init__(
        self,
        config: TushareProbeConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._last_request_at = 0.0
        self._pace_lock = asyncio.Lock()

    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        await self._pace()
        received_at = datetime.now(UTC)
        request_identity = content_hash(
            {
                "api_name": api_name,
                "params": dict(params),
                "fields": list(fields),
                "received_at": received_at,
            }
        )
        body = await self._request(api_name, params, fields)
        decoded_fields, rows = _decode(body)
        return ProviderTable(
            api_name=api_name,
            fields=decoded_fields,
            rows=rows,
            raw_body=body,
            request_identity=request_identity,
            received_at=received_at,
            source_endpoint=_endpoint_identity(self._config.api_url),
        )

    async def _pace(self) -> None:
        async with self._pace_lock:
            interval = 60.0 / self._config.rate_limit_per_minute
            delay = self._last_request_at + interval - monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request_at = monotonic()

    async def _request(
        self,
        api_name: str,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> object:
        payload: dict[str, object] = {
            "api_name": api_name,
            "token": self._config.token.get_secret_value(),
            "params": dict(params),
            "fields": ",".join(fields),
        }
        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._post(payload)
                if response.status_code == 429 or response.status_code >= 500:
                    raise TushareRequestError(
                        "provider_temporarily_unavailable",
                        recoverable=True,
                    )
                if response.status_code >= 400:
                    raise TushareRequestError("provider_rejected")
                body: object = response.json()
                _validate(body)
                return body
            except (httpx.TimeoutException, httpx.TransportError, ValueError) as error:
                if attempt >= self._config.max_retries:
                    code = (
                        "timeout"
                        if isinstance(error, httpx.TimeoutException)
                        else "transport_error"
                    )
                    raise TushareRequestError(code) from error
            except TushareRequestError as error:
                if not error.recoverable or attempt >= self._config.max_retries:
                    raise
            await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
        raise AssertionError("unreachable")

    async def _post(self, payload: dict[str, object]) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(
                self._config.api_url,
                json=payload,
                timeout=self._config.timeout_seconds,
            )
        async with httpx.AsyncClient(follow_redirects=True) as client:
            return await client.post(
                self._config.api_url,
                json=payload,
                timeout=self._config.timeout_seconds,
            )


def _validate(body: object) -> None:
    if not isinstance(body, dict):
        raise TushareRequestError("invalid_response")
    if body.get("code") == 0:
        return
    message = str(body.get("msg", "")).lower()
    if any(marker in message for marker in ("权限", "permission", "积分")):
        raise TushareRequestError("permission_denied")
    raise TushareRequestError("provider_error")


def _decode(body: object) -> tuple[tuple[str, ...], tuple[dict[str, object], ...]]:
    if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        raise TushareRequestError("invalid_response")
    data = body["data"]
    fields = data.get("fields")
    items = data.get("items")
    if not isinstance(fields, list) or not isinstance(items, list):
        raise TushareRequestError("invalid_response")
    names = tuple(str(field) for field in fields)
    rows = tuple(dict(zip(names, row, strict=False)) for row in items if isinstance(row, list))
    return names, rows


def _endpoint_identity(url: str) -> str:
    parsed = httpx.URL(url)
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.host}{port}{parsed.path}"


__all__ = ["TushareHttpClient", "TushareRequestError"]
