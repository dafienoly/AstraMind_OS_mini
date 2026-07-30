"""Canonical batch adapter backed by the persistent MiniQMT bridge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ..application.identity import content_hash
from ..contracts.source import (
    CanonicalDatasetRequest,
    ProviderBatch,
    SourceHealth,
    SourceHealthState,
)
from .miniqmt_bridge import MiniQMTBridgeClient, MiniQMTBridgeError


class MiniQMTSourceAdapter:
    provider_id = "miniqmt"
    market_batch_size = 200

    def __init__(self, bridge: MiniQMTBridgeClient) -> None:
        self._bridge = bridge

    async def capabilities(self) -> frozenset[str]:
        return frozenset(
            {
                "daily_market",
                "broad_index_daily",
                "minute_market",
                "instrument_snapshot",
                "trade_calendar_check",
                "index_constituent_weight_current",
                "sector_membership_current",
                "sector_catalog_current",
                "financial_statement",
                "shareholder_count",
                "top10_holder",
                "top10_float_holder",
                "corporate_action_factor",
            }
        )

    async def fetch(self, request: CanonicalDatasetRequest) -> ProviderBatch:
        if request.dataset_name in {"daily_market", "broad_index_daily", "minute_market"} and len(
            request.universe
        ) > self._market_batch_size(request):
            return await self._fetch_market_chunks(request)
        return await self._fetch_direct(request)

    async def _fetch_direct(self, request: CanonicalDatasetRequest) -> ProviderBatch:
        filters: dict[str, object] = dict(request.filters)
        if request.start_date is not None:
            filters.setdefault("start_time", request.start_date.strftime("%Y%m%d"))
        if request.end_date is not None:
            filters.setdefault("end_time", request.end_date.strftime("%Y%m%d"))
        if request.dataset_name in {"daily_market", "broad_index_daily"}:
            filters.setdefault("matrix", True)
            if request.start_date is not None:
                if request.start_date == request.end_date:
                    filters["start_time"] = ""
                    filters.setdefault("count", 2)
                else:
                    filters["start_time"] = (request.start_date - timedelta(days=10)).strftime(
                        "%Y%m%d"
                    )
        payload = {
            **request.model_dump(mode="json"),
            "filters": filters,
        }
        result = await self._bridge.request("fetch", request=payload)
        canonical_rows = _canonical_rows(result, request)
        missing = _missing_single_day_universe(canonical_rows, request)
        cache_preparations = await self._prepare_single_day_cache(request, missing)
        if cache_preparations:
            result = await self._bridge.request("fetch", request=payload)
            canonical_rows = _canonical_rows(result, request)
        rows = result.get("rows", [])
        if not isinstance(rows, list):
            raise MiniQMTBridgeError("bridge_rows_invalid")
        raw = result.get("raw_payload")
        retrieved_at = datetime.fromisoformat(str(result["retrieved_at"]))
        request_identity = content_hash(
            {
                "request": request.model_dump(mode="json"),
                "provider_version": result.get("provider_version"),
                "cache_preparations": cache_preparations,
                "raw": raw,
            }
        )
        latency = result.get("latency_breakdown_ms", {})
        return ProviderBatch(
            provider_id=self.provider_id,
            provider_version=str(result.get("provider_version", self._bridge.provider_version)),
            native_interface=("download_history_data2+" if cache_preparations else "")
            + str(result.get("native_interface", "unknown")),
            source_endpoint=("windows-xtdata-local-ndjson:" + self._bridge.client_fingerprint[:16]),
            request_identity=request_identity,
            retrieved_at=retrieved_at,
            rows=canonical_rows,
            raw_payload=raw,
            completeness=1.0 if rows else 0.0,
            latency_breakdown_ms=latency if isinstance(latency, dict) else {},
        )

    async def _prepare_single_day_cache(
        self,
        request: CanonicalDatasetRequest,
        missing_universe: tuple[str, ...],
    ) -> tuple[dict[str, object], ...]:
        if (
            request.dataset_name not in {"daily_market", "broad_index_daily"}
            or request.start_date is None
            or request.start_date != request.end_date
            or not missing_universe
        ):
            return ()
        target = request.start_date.strftime("%Y%m%d")
        preparations: list[dict[str, object]] = []
        cache_batch_size = 100
        for offset in range(0, len(missing_universe), cache_batch_size):
            universe = missing_universe[offset : offset + cache_batch_size]
            result = await self._bridge.request(
                "prepare_history_cache",
                timeout_seconds=120,
                universe=universe,
                period="1d",
                start_time=target,
                end_time=target,
            )
            preparations.append(
                {
                    "native_interface": result.get(
                        "native_interface",
                        "download_history_data2",
                    ),
                    "instrument_count": len(universe),
                    "started_at": result.get("started_at"),
                    "ended_at": result.get("ended_at"),
                }
            )
        return tuple(preparations)

    async def _fetch_market_chunks(
        self,
        request: CanonicalDatasetRequest,
    ) -> ProviderBatch:
        batches = []
        batch_size = self._market_batch_size(request)
        for offset in range(0, len(request.universe), batch_size):
            universe = request.universe[offset : offset + batch_size]
            batches.append(
                await self._fetch_direct(request.model_copy(update={"universe": universe}))
            )
        rows = tuple(row for batch in batches for row in batch.rows)
        return ProviderBatch(
            provider_id=self.provider_id,
            provider_version=batches[0].provider_version,
            native_interface=batches[0].native_interface + "-chunked",
            source_endpoint=batches[0].source_endpoint,
            request_identity=content_hash(
                {
                    "request": request.model_dump(mode="json"),
                    "parts": [batch.request_identity for batch in batches],
                }
            ),
            retrieved_at=max(batch.retrieved_at for batch in batches),
            rows=rows,
            raw_payload=tuple(batch.raw_payload for batch in batches),
            completeness=min(batch.completeness for batch in batches),
            known_gaps=tuple(gap for batch in batches for gap in batch.known_gaps),
            latency_breakdown_ms={
                "provider": sum(batch.latency_breakdown_ms.get("provider", 0) for batch in batches),
                "bridge_batches": float(len(batches)),
            },
        )

    def _market_batch_size(self, request: CanonicalDatasetRequest) -> int:
        if (
            request.dataset_name in {"daily_market", "broad_index_daily"}
            and request.start_date is not None
            and request.end_date is not None
        ):
            span = (request.end_date - request.start_date).days
            if span <= 10:
                return 6000
            if span <= 45:
                return 1000
        return self.market_batch_size

    async def health(self) -> SourceHealth:
        started = datetime.now(UTC)
        try:
            result = await self._bridge.request("health", timeout_seconds=3)
        except MiniQMTBridgeError as error:
            return SourceHealth(
                provider_id=self.provider_id,
                provider_version=self._bridge.provider_version,
                state=SourceHealthState.DISCONNECTED,
                checked_at=datetime.now(UTC),
                known_gaps=(error.code,),
            )
        ended = datetime.now(UTC)
        return SourceHealth(
            provider_id=self.provider_id,
            provider_version=str(result.get("provider_version", "unknown")),
            state=SourceHealthState.HEALTHY,
            checked_at=ended,
            latency_ms=(ended - started).total_seconds() * 1000,
        )


def _canonical_market_row(row: dict[str, object], dataset: str) -> dict[str, object]:
    aliases = {
        "preClose": "previous_close",
        "lastClose": "previous_close",
        "vol": "volume",
        "pctChg": "percent_change",
    }
    result = {aliases.get(field, field): value for field, value in row.items()}
    value = result.get("time")
    if dataset in {"daily_market", "broad_index_daily"} and isinstance(value, int | float):
        result["trade_date"] = datetime.fromtimestamp(
            float(value) / 1000,
            tz=ZoneInfo("Asia/Shanghai"),
        ).strftime("%Y%m%d")
    return result


def _canonical_rows(
    result: dict[str, object],
    request: CanonicalDatasetRequest,
) -> tuple[dict[str, object], ...]:
    rows = result.get("rows", [])
    if not isinstance(rows, list):
        raise MiniQMTBridgeError("bridge_rows_invalid")
    canonical = tuple(
        _canonical_market_row(row, request.dataset_name)
        for row in rows
        if isinstance(row, dict)
    )
    return _filter_requested_dates(canonical, request)


def _missing_single_day_universe(
    rows: tuple[dict[str, object], ...],
    request: CanonicalDatasetRequest,
) -> tuple[str, ...]:
    if (
        request.dataset_name not in {"daily_market", "broad_index_daily"}
        or request.start_date is None
        or request.start_date != request.end_date
        or not request.universe
    ):
        return ()
    present = {
        str(row.get("instrument_id"))
        for row in rows
        if row.get("instrument_id") not in (None, "")
    }
    return tuple(instrument for instrument in request.universe if instrument not in present)


def _filter_requested_dates(
    rows: tuple[dict[str, object], ...],
    request: CanonicalDatasetRequest,
) -> tuple[dict[str, object], ...]:
    if (
        request.dataset_name not in {"daily_market", "broad_index_daily"}
        or request.start_date is None
        or request.end_date is None
    ):
        return rows
    start = request.start_date.strftime("%Y%m%d")
    end = request.end_date.strftime("%Y%m%d")
    return tuple(row for row in rows if start <= str(row.get("trade_date", "")) <= end)


__all__ = ["MiniQMTSourceAdapter"]
