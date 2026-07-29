"""Canonical dataset adapter for the Tushare-compatible HTTP client."""

from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic

from ..application.identity import content_hash
from ..contracts.source import (
    CanonicalDatasetRequest,
    ProviderBatch,
    SourceHealth,
    SourceHealthState,
)
from .tushare_client import TushareHttpClient

DATASET_INTERFACES = {
    "trade_calendar": "trade_cal",
    "daily_market": "daily",
    "broad_index_daily": "index_daily",
    "industry_index_daily": "sw_daily",
    "security_master": "stock_basic",
    "security_name_history": "namechange",
    "corporate_action": "dividend",
    "adjustment_factor": "adj_factor",
    "daily_basic": "daily_basic",
    "price_limit": "stk_limit",
    "suspension_event": "suspend_d",
    "lhb_event": "top_list",
    "lhb_seat": "top_inst",
    "shareholder_count": "stk_holdernumber",
    "industry_taxonomy": "index_classify",
    "industry_membership": "index_member_all",
}

CANONICAL_FIELDS = {
    "instrument_id": "ts_code",
    "trade_date": "trade_date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "previous_close": "pre_close",
    "change": "change",
    "percent_change": "pct_chg",
    "volume": "vol",
    "amount": "amount",
}


class TushareSourceAdapter:
    provider_id = "tushare"

    def __init__(
        self,
        client: TushareHttpClient,
        *,
        version: str = "http-v1",
        allowed_datasets: frozenset[str] | None = None,
    ) -> None:
        self._client = client
        self._version = version
        self._allowed_datasets = allowed_datasets

    async def capabilities(self) -> frozenset[str]:
        capabilities = frozenset(DATASET_INTERFACES)
        return (
            capabilities
            if self._allowed_datasets is None
            else capabilities & self._allowed_datasets
        )

    async def fetch(self, request: CanonicalDatasetRequest) -> ProviderBatch:
        interface = DATASET_INTERFACES.get(request.dataset_name)
        if interface is None or (
            self._allowed_datasets is not None
            and request.dataset_name not in self._allowed_datasets
        ):
            raise ValueError(f"unsupported_dataset:{request.dataset_name}")
        if len(request.universe) > 1:
            return await self._fetch_many(request, interface)
        return await self._fetch_one(request, interface)

    async def _fetch_one(
        self,
        request: CanonicalDatasetRequest,
        interface: str,
    ) -> ProviderBatch:
        params = _params(request)
        started = monotonic()
        provider_fields = tuple(CANONICAL_FIELDS.get(field, field) for field in request.fields)
        table = await self._client.query(interface, params=params, fields=provider_fields)
        fetch_ms = (monotonic() - started) * 1000
        rows = tuple(_canonical_row(row, request.dataset_name) for row in table.rows)
        return ProviderBatch(
            provider_id=self.provider_id,
            provider_version=self._version,
            native_interface=interface,
            source_endpoint=table.source_endpoint,
            request_identity=table.request_identity,
            retrieved_at=table.received_at,
            rows=rows,
            raw_payload=table.raw_body,
            completeness=1.0 if table.rows else 0.0,
            latency_breakdown_ms={"fetch": fetch_ms},
        )

    async def _fetch_many(
        self,
        request: CanonicalDatasetRequest,
        interface: str,
    ) -> ProviderBatch:
        if (
            request.dataset_name == "daily_market"
            and request.start_date is not None
            and request.start_date == request.end_date
        ):
            return await self._fetch_daily_cross_section(request, interface)
        started = monotonic()
        batches = []
        for instrument_id in request.universe:
            single = request.model_copy(update={"universe": (instrument_id,)})
            batches.append(await self._fetch_one(single, interface))
        rows = tuple(row for batch in batches for row in batch.rows)
        request_identity = content_hash(
            {
                "request": request.model_dump(mode="json"),
                "parts": [batch.request_identity for batch in batches],
            }
        )
        return ProviderBatch(
            provider_id=self.provider_id,
            provider_version=self._version,
            native_interface=interface,
            source_endpoint=batches[0].source_endpoint,
            request_identity=request_identity,
            retrieved_at=max(batch.retrieved_at for batch in batches),
            rows=rows,
            raw_payload=tuple(batch.raw_payload for batch in batches),
            completeness=sum(bool(batch.rows) for batch in batches) / len(batches),
            known_gaps=tuple(
                f"empty_instrument:{instrument_id}"
                for instrument_id, batch in zip(request.universe, batches, strict=True)
                if not batch.rows
            ),
            latency_breakdown_ms={"fetch": (monotonic() - started) * 1000},
        )

    async def _fetch_daily_cross_section(
        self,
        request: CanonicalDatasetRequest,
        interface: str,
    ) -> ProviderBatch:
        batch = await self._fetch_one(request.model_copy(update={"universe": ()}), interface)
        requested = frozenset(request.universe)
        rows = tuple(row for row in batch.rows if str(row.get("instrument_id")) in requested)
        observed = {str(row.get("instrument_id")) for row in rows}
        missing = tuple(sorted(requested - observed))
        return batch.model_copy(
            update={
                "rows": rows,
                "completeness": len(observed) / len(requested),
                "known_gaps": tuple(
                    f"empty_instrument:{instrument_id}" for instrument_id in missing
                ),
                "request_identity": content_hash(
                    {
                        "request": request.model_dump(mode="json"),
                        "provider_request_identity": batch.request_identity,
                    }
                ),
            }
        )

    async def health(self) -> SourceHealth:
        return SourceHealth(
            provider_id=self.provider_id,
            provider_version=self._version,
            state=SourceHealthState.HEALTHY,
            checked_at=datetime.now(UTC),
        )


def _params(request: CanonicalDatasetRequest) -> dict[str, object]:
    result: dict[str, object] = dict(request.filters)
    trade_date_datasets = {
        "daily_market",
        "daily_basic",
        "price_limit",
        "suspension_event",
        "lhb_event",
        "lhb_seat",
    }
    if (
        request.dataset_name in trade_date_datasets
        and request.start_date is not None
        and request.start_date == request.end_date
    ):
        result["trade_date"] = request.start_date.strftime("%Y%m%d")
    else:
        if request.start_date is not None:
            result["start_date"] = request.start_date.strftime("%Y%m%d")
        if request.end_date is not None:
            result["end_date"] = request.end_date.strftime("%Y%m%d")
    if len(request.universe) == 1:
        result.setdefault("ts_code", request.universe[0])
    return result


def _canonical_row(row: dict[str, object], dataset: str) -> dict[str, object]:
    reverse = {value: key for key, value in CANONICAL_FIELDS.items()}
    result = {reverse.get(field, field): value for field, value in row.items()}
    amount = result.get("amount")
    if dataset in {"daily_market", "broad_index_daily"} and isinstance(amount, int | float):
        result["amount"] = float(amount) * 1000
    return result


__all__ = ["DATASET_INTERFACES", "TushareSourceAdapter"]
