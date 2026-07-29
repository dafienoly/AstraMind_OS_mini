"""Freeze source routes and perform whole-batch failover."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from time import monotonic

from ..contracts.source import (
    CanonicalDatasetRequest,
    DatasetSourceRoute,
    ProviderBatch,
    SourceSelectionEvidence,
)
from ..ports import BatchDataSourceAdapter, RawRecordStore
from .identity import content_hash
from .raw_records import preserve_provider_batch_raw

BatchValidator = Callable[[CanonicalDatasetRequest, ProviderBatch], None]


class SourceRouteError(RuntimeError):
    def __init__(self, code: str, attempts: tuple[str, ...]) -> None:
        super().__init__(code)
        self.code = code
        self.attempts = attempts


@dataclass(frozen=True, slots=True)
class RoutedBatch:
    batch: ProviderBatch
    evidence: SourceSelectionEvidence


class DatasetSourceRouter:
    def __init__(
        self,
        *,
        adapters: Mapping[str, BatchDataSourceAdapter],
        routes: tuple[DatasetSourceRoute, ...],
        raw_store: RawRecordStore,
        validators: Mapping[str, BatchValidator] | None = None,
    ) -> None:
        self._adapters = dict(adapters)
        self._routes = {item.dataset_name: item for item in routes}
        if len(self._routes) != len(routes):
            raise ValueError("规范数据集路由重复")
        missing = {
            provider
            for route in routes
            for provider in route.providers
            if provider not in self._adapters
        }
        if missing:
            raise ValueError("数据源适配器未注册：" + ",".join(sorted(missing)))
        self._raw_store = raw_store
        self._validators = dict(validators or {})
        self.route_hash = content_hash(
            [
                route.model_dump(mode="json")
                for route in sorted(routes, key=lambda x: x.dataset_name)
            ]
        )

    async def fetch(self, request: CanonicalDatasetRequest) -> RoutedBatch:
        route = self._routes.get(request.dataset_name)
        if route is None:
            raise SourceRouteError("route_not_configured", ())
        attempts: list[str] = []
        last_code = "all_sources_failed"
        started = monotonic()
        for provider_id in _providers_for(route, request):
            attempts.append(provider_id)
            adapter = self._adapters[provider_id]
            try:
                async with asyncio.timeout(route.timeout_seconds):
                    batch = await adapter.fetch(request)
            except TimeoutError:
                last_code = "source_timeout"
                continue
            except Exception as error:
                last_code = getattr(error, "code", type(error).__name__.lower())
                continue
            try:
                self._preserve_raw(batch)
            except Exception as error:
                raise SourceRouteError(
                    f"raw_record_integrity:{type(error).__name__.lower()}",
                    tuple(attempts),
                ) from error
            try:
                self._validate(route, request, batch)
            except Exception as error:
                last_code = getattr(error, "code", str(error) or type(error).__name__.lower())
                continue
            evidence = SourceSelectionEvidence(
                dataset_name=request.dataset_name,
                route_hash=self.route_hash,
                selected_provider=batch.provider_id,
                attempted_providers=tuple(attempts),
                fallback_reason=last_code if len(attempts) > 1 else None,
                selected_request_identity=batch.request_identity,
                selected_content_hash=content_hash(batch.rows),
                fetch_ms=(monotonic() - started) * 1000,
                fallback_count=len(attempts) - 1,
                recorded_at=datetime.now(UTC),
            )
            return RoutedBatch(batch=batch, evidence=evidence)
        raise SourceRouteError(last_code, tuple(attempts))

    def _validate(
        self,
        route: DatasetSourceRoute,
        request: CanonicalDatasetRequest,
        batch: ProviderBatch,
    ) -> None:
        if batch.provider_id not in route.providers:
            raise ValueError("适配器返回了路由外提供方")
        if not route.allow_empty and not request.allow_empty and not batch.rows:
            raise ValueError("source_empty")
        if batch.rows and batch.completeness < 1:
            raise ValueError(f"source_incomplete:{batch.completeness:.6f}")
        missing = {
            field for field in route.required_fields if any(field not in row for row in batch.rows)
        }
        if missing:
            raise ValueError("required_fields_missing:" + ",".join(sorted(missing)))
        if route.primary_key:
            identities = [
                tuple(row.get(field) for field in route.primary_key) for row in batch.rows
            ]
            if len(identities) != len(set(identities)):
                raise ValueError("duplicate_primary_key")
        if request.universe:
            requested = set(request.universe)
            if any(
                str(row.get("instrument_id") or row.get("ts_code")) not in requested
                for row in batch.rows
            ):
                raise ValueError("record_outside_requested_universe")
        for row in batch.rows:
            observed_on = _row_date(row)
            if (
                observed_on is not None
                and request.start_date is not None
                and observed_on < request.start_date
            ):
                raise ValueError("record_before_requested_range")
            if (
                observed_on is not None
                and request.end_date is not None
                and observed_on > request.end_date
            ):
                raise ValueError("record_after_requested_range")
        validator = self._validators.get(request.dataset_name)
        if validator is not None:
            validator(request, batch)

    def _preserve_raw(self, batch: ProviderBatch) -> None:
        preserve_provider_batch_raw(batch, self._raw_store)


def _row_date(row: dict[str, object]) -> date | None:
    value = row.get("trade_date") or row.get("observed_on")
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    text = "".join(character for character in str(value) if character.isdigit())
    if len(text) < 8:
        return None
    return date.fromisoformat(f"{text[:4]}-{text[4:6]}-{text[6:8]}")


def _providers_for(
    route: DatasetSourceRoute,
    request: CanonicalDatasetRequest,
) -> tuple[str, ...]:
    if not route.provider_lineage or (request.start_date is None and request.end_date is None):
        return route.providers
    start = request.start_date or request.end_date
    end = request.end_date or request.start_date
    assert start is not None and end is not None
    matches = tuple(
        epoch.provider
        for epoch in route.provider_lineage
        if start >= epoch.effective_from
        and (epoch.effective_to is None or end <= epoch.effective_to)
    )
    if len(matches) != 1:
        raise SourceRouteError("request_crosses_provider_cutover", ())
    if matches[0] not in route.providers:
        raise SourceRouteError("provider_epoch_not_registered", ())
    return matches


__all__ = ["DatasetSourceRouter", "RoutedBatch", "SourceRouteError"]
