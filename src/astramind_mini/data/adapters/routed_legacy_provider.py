"""Compatibility facade while collectors migrate to canonical requests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime

from ..application.source_router import DatasetSourceRouter
from ..contracts.source import CanonicalDatasetRequest, SourceSelectionEvidence
from ..ports import ProviderTable
from .tushare_source import CANONICAL_FIELDS, DATASET_INTERFACES

INTERFACE_DATASETS = {value: key for key, value in DATASET_INTERFACES.items()}
NATIVE_TO_CANONICAL = {value: key for key, value in CANONICAL_FIELDS.items()}


class RoutedHistoricalProvider:
    def __init__(self, router: DatasetSourceRouter) -> None:
        self._router = router
        self.selection_evidence: list[SourceSelectionEvidence] = []

    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        dataset = INTERFACE_DATASETS.get(api_name)
        if dataset is None:
            raise ValueError(f"canonical_dataset_not_mapped:{api_name}")
        start = _provider_date(params.get("start_date") or params.get("trade_date"))
        end = _provider_date(params.get("end_date") or params.get("trade_date"))
        instrument = params.get("ts_code")
        requested_universe = params.get("universe")
        universe = (
            tuple(str(value) for value in requested_universe)
            if isinstance(requested_universe, tuple | list)
            else (str(instrument),)
            if instrument
            else ()
        )
        filters: dict[str, str | int | bool | tuple[str, ...]] = {
            key: value
            for key, value in params.items()
            if key not in {"start_date", "end_date", "trade_date", "ts_code", "universe"}
            and isinstance(value, str | int | bool)
        }
        request = CanonicalDatasetRequest(
            dataset_name=dataset,
            as_of=datetime.now(UTC),
            start_date=start,
            end_date=end,
            universe=universe,
            fields=tuple(NATIVE_TO_CANONICAL.get(field, field) for field in fields),
            filters=filters,
            allow_empty=_allow_empty(api_name, params),
        )
        routed = await self._router.fetch(request)
        self.selection_evidence.append(routed.evidence)
        batch = routed.batch
        return ProviderTable(
            api_name=api_name,
            fields=tuple(fields),
            rows=tuple(_legacy_row(row, api_name) for row in batch.rows),
            raw_body=batch.raw_payload,
            request_identity=batch.request_identity,
            received_at=batch.retrieved_at,
            source_endpoint=batch.source_endpoint,
            provider_id=batch.provider_id,
            provider_version=batch.provider_version,
            raw_record_persisted=True,
        )


def _provider_date(value: object) -> date | None:
    if value is None:
        return None
    return datetime.strptime(str(value), "%Y%m%d").date()


def _allow_empty(api_name: str, params: Mapping[str, object]) -> bool:
    return api_name == "stock_basic" and params.get("list_status") == "P"


def _legacy_row(row: dict[str, object], api_name: str) -> dict[str, object]:
    result = {CANONICAL_FIELDS.get(field, field): value for field, value in row.items()}
    amount = result.get("amount")
    if api_name in {"daily", "index_daily", "sw_daily"} and isinstance(amount, int | float):
        result["amount"] = float(amount) / 1000
    return result


__all__ = ["RoutedHistoricalProvider"]
