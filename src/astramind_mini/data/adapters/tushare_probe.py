"""Small, credential-safe Tushare-compatible capability probe."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from time import monotonic

import httpx

from ..application.identity import content_hash, schema_fingerprint
from ..contracts import (
    CapabilityState,
    ProbeReport,
    ProviderCapability,
    RawRecordEnvelope,
)
from .provider_config import TushareProbeConfig

PROBES = {
    "trade_cal": ("exchange,cal_date,is_open", {}),
    "stock_basic": ("ts_code,symbol,name,area,industry,list_date", {"ts_code": "000001.SZ"}),
    "daily": ("ts_code,trade_date,open,high,low,close,vol,amount", {"ts_code": "000001.SZ"}),
    "adj_factor": ("ts_code,trade_date,adj_factor", {"ts_code": "000001.SZ"}),
    "daily_basic": ("ts_code,trade_date,turnover_rate,total_mv,circ_mv", {"ts_code": "000001.SZ"}),
}


class TushareCapabilityProbe:
    def __init__(self, config: TushareProbeConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        self._client = client

    async def probe(
        self,
    ) -> tuple[ProbeReport, tuple[tuple[RawRecordEnvelope, object], ...]]:
        capabilities: list[ProviderCapability] = []
        records: list[tuple[RawRecordEnvelope, object]] = []
        probed_at = datetime.now(UTC)
        trade_date = (probed_at.date() - timedelta(days=1)).strftime("%Y%m%d")
        for index, (api_name, (fields, base_params)) in enumerate(PROBES.items()):
            if index:
                await asyncio.sleep(60.0 / self._config.rate_limit_per_minute)
            params = dict(base_params)
            if api_name == "trade_cal":
                params.update(
                    start_date=(probed_at.date() - timedelta(days=14)).strftime("%Y%m%d"),
                    end_date=trade_date,
                )
            elif api_name != "stock_basic":
                params["trade_date"] = trade_date
            capability, raw = await self._probe_one(api_name, params, fields, probed_at)
            capabilities.append(capability)
            if raw is not None:
                records.append(raw)
                if api_name == "trade_cal":
                    trade_date = _latest_open_date(raw[1]) or trade_date
        identity = {
            "provider": "tushare",
            "probed_at": probed_at,
            "capabilities": [item.model_dump(mode="json") for item in capabilities],
        }
        report = ProbeReport(
            probe_id=content_hash(identity),
            provider="tushare",
            gateway_version="wp-0002a-v1",
            client_version=f"httpx-{httpx.__version__}",
            probed_at=probed_at,
            capabilities=tuple(capabilities),
            known_gaps=tuple(
                item.capability_id
                for item in capabilities
                if item.state is not CapabilityState.AVAILABLE
            ),
        )
        return report, tuple(records)

    async def _probe_one(
        self,
        api_name: str,
        params: dict[str, str],
        fields: str,
        received_at: datetime,
    ) -> tuple[ProviderCapability, tuple[RawRecordEnvelope, object] | None]:
        started = monotonic()
        request_identity = content_hash(
            {
                "api_name": api_name,
                "params": params,
                "fields": fields,
                "received_at": received_at,
            }
        )
        try:
            body = await self._request(api_name, params, fields)
            rows = _decode_rows(body)
            state = CapabilityState.AVAILABLE if rows else CapabilityState.EMPTY
            observed_fields = tuple(sorted({key for row in rows for key in row}))
            capability = ProviderCapability(
                capability_id=f"tushare:{api_name}",
                interface_name=api_name,
                state=state,
                interface_present=True,
                configured=True,
                permission_available=True,
                data_available=bool(rows),
                observed_fields=observed_fields,
                row_count=len(rows),
                latency_ms=int((monotonic() - started) * 1000),
                schema_fingerprint=schema_fingerprint(rows),
                coverage_summary=f"small-sample:{len(rows)}",
            )
            envelope = RawRecordEnvelope(
                provider="tushare",
                interface_name=api_name,
                source_endpoint=_endpoint_identity(self._config.api_url),
                request_identity=request_identity,
                received_at=received_at,
                schema_version="provider-v1",
                content_hash=content_hash(body),
            )
            return capability, (envelope, body)
        except ProbeFailure as error:
            permission = error.code == "permission_denied"
            state = CapabilityState.PERMISSION_DENIED if permission else CapabilityState.ERROR
            return (
                ProviderCapability(
                    capability_id=f"tushare:{api_name}",
                    interface_name=api_name,
                    state=state,
                    interface_present=True,
                    configured=True,
                    permission_available=False if permission else None,
                    data_available=False,
                    latency_ms=int((monotonic() - started) * 1000),
                    error_code=error.code,
                    known_gaps=(error.code,),
                ),
                None,
            )

    async def _request(
        self,
        api_name: str,
        params: dict[str, str],
        fields: str,
    ) -> object:
        payload = {
            "api_name": api_name,
            "token": self._config.token.get_secret_value(),
            "params": params,
            "fields": fields,
        }
        for attempt in range(self._config.max_retries + 1):
            try:
                if self._client is not None:
                    response = await self._client.post(
                        self._config.api_url,
                        json=payload,
                        timeout=self._config.timeout_seconds,
                    )
                else:
                    async with httpx.AsyncClient(follow_redirects=True) as client:
                        response = await client.post(
                            self._config.api_url,
                            json=payload,
                            timeout=self._config.timeout_seconds,
                        )
                if response.status_code == 429 or response.status_code >= 500:
                    raise ProbeFailure("provider_temporarily_unavailable")
                if response.status_code >= 400:
                    raise ProbeFailure("provider_rejected")
                body: object = response.json()
                _validate_provider_response(body)
                return body
            except (httpx.TimeoutException, httpx.TransportError, ValueError) as error:
                if attempt >= self._config.max_retries:
                    code = (
                        "timeout"
                        if isinstance(error, httpx.TimeoutException)
                        else "transport_error"
                    )
                    raise ProbeFailure(code) from error
                await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
            except ProbeFailure as error:
                if error.code != "provider_temporarily_unavailable":
                    raise
                if attempt >= self._config.max_retries:
                    raise
                await asyncio.sleep(min(0.25 * (2**attempt), 1.0))
        raise AssertionError("unreachable")


class ProbeFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _validate_provider_response(body: object) -> None:
    if not isinstance(body, dict):
        raise ProbeFailure("invalid_response")
    code = body.get("code")
    if code == 0:
        return
    message = str(body.get("msg", "")).lower()
    if any(marker in message for marker in ("权限", "permission", "积分")):
        raise ProbeFailure("permission_denied")
    raise ProbeFailure("provider_error")


def _decode_rows(body: object) -> list[dict[str, object]]:
    if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        raise ProbeFailure("invalid_response")
    data = body["data"]
    fields = data.get("fields")
    items = data.get("items")
    if not isinstance(fields, list) or not isinstance(items, list):
        raise ProbeFailure("invalid_response")
    names = [str(field) for field in fields]
    return [dict(zip(names, row, strict=False)) for row in items if isinstance(row, list)]


def _endpoint_identity(url: str) -> str:
    parsed = httpx.URL(url)
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.host}{port}{parsed.path}"


def _latest_open_date(body: object) -> str | None:
    rows = _decode_rows(body)
    open_dates = [
        str(row["cal_date"])
        for row in rows
        if str(row.get("is_open", "0")) == "1" and row.get("cal_date")
    ]
    return max(open_dates, default=None)


__all__ = ["TushareCapabilityProbe"]
