"""Repeat canonical provider requests and publish a machine-readable benchmark."""

from __future__ import annotations

import contextlib
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from statistics import median, quantiles
from time import monotonic

from ..contracts.source import (
    BenchmarkSample,
    BenchmarkScenario,
    BenchmarkStatistics,
    CanonicalDatasetRequest,
    ProviderBenchmarkReport,
)
from ..ports import BatchDataSourceAdapter
from .identity import content_hash

Stage = Callable[[object], Awaitable[None]]


async def benchmark_sources(
    *,
    adapters: Mapping[str, BatchDataSourceAdapter],
    requests: tuple[CanonicalDatasetRequest, ...],
    repetitions: int,
    cache_state: str,
    normalize: Stage | None = None,
    persist: Stage | None = None,
    environment: Mapping[str, str] | None = None,
) -> ProviderBenchmarkReport:
    if not 1 <= repetitions <= 100:
        raise ValueError("测速重复次数必须在 1 到 100 之间")
    started_at = datetime.now(UTC)
    samples: list[BenchmarkSample] = []
    for request in requests:
        scenario_id = content_hash(request.model_dump(mode="json"))
        for provider_id, adapter in adapters.items():
            if request.dataset_name not in await adapter.capabilities():
                continue
            if cache_state == "warm":
                with contextlib.suppress(Exception):
                    await adapter.fetch(request)
            for _ in range(repetitions):
                total_started = monotonic()
                fetch_started = monotonic()
                try:
                    batch = await adapter.fetch(request)
                    fetch_ms = (monotonic() - fetch_started) * 1000
                    normalize_started = monotonic()
                    if normalize is not None:
                        await normalize(batch)
                    normalize_ms = (monotonic() - normalize_started) * 1000
                    persist_started = monotonic()
                    if persist is not None:
                        await persist(batch)
                    persist_ms = (monotonic() - persist_started) * 1000
                    error_code = None
                    rows = len(batch.rows)
                except Exception as error:
                    fetch_ms = (monotonic() - fetch_started) * 1000
                    normalize_ms = persist_ms = 0
                    error_code = getattr(error, "code", type(error).__name__.lower())
                    rows = 0
                samples.append(
                    BenchmarkSample(
                        provider_id=provider_id,
                        dataset_name=request.dataset_name,
                        scenario_id=scenario_id,
                        cache_state=cache_state,
                        row_count=rows,
                        total_ms=(monotonic() - total_started) * 1000,
                        fetch_ms=fetch_ms,
                        normalize_ms=normalize_ms,
                        persist_ms=persist_ms,
                        error_code=error_code,
                    )
                )
    ended_at = datetime.now(UTC)
    identity = {
        "version": "provider-benchmark-v1",
        "started_at": started_at,
        "ended_at": ended_at,
        "requests": [item.model_dump(mode="json") for item in requests],
        "samples": [item.model_dump(mode="json") for item in samples],
    }
    return ProviderBenchmarkReport(
        benchmark_id=content_hash(identity),
        benchmark_version="provider-benchmark-v1",
        started_at=started_at,
        ended_at=ended_at,
        environment=dict(environment or {}),
        scenarios=tuple(
            BenchmarkScenario(
                scenario_id=content_hash(request.model_dump(mode="json")),
                dataset_name=request.dataset_name,
                start_date=request.start_date,
                end_date=request.end_date,
                universe_count=len(request.universe),
                frequency=request.frequency,
                adjustment=request.adjustment,
            )
            for request in requests
        ),
        samples=tuple(samples),
        statistics=_statistics(tuple(samples)),
        conclusions={},
    )


def _statistics(samples: tuple[BenchmarkSample, ...]) -> tuple[BenchmarkStatistics, ...]:
    groups: dict[tuple[str, str, str], list[BenchmarkSample]] = {}
    for sample in samples:
        key = (sample.provider_id, sample.dataset_name, sample.scenario_id)
        groups.setdefault(key, []).append(sample)
    result = []
    for (provider_id, dataset_name, scenario_id), values in sorted(groups.items()):
        elapsed = [value.total_ms for value in values]
        total_ms = sum(elapsed)
        result.append(
            BenchmarkStatistics(
                provider_id=provider_id,
                dataset_name=dataset_name,
                scenario_id=scenario_id,
                sample_count=len(values),
                p50_ms=median(elapsed),
                p95_ms=_percentile(elapsed, 95),
                p99_ms=_percentile(elapsed, 99),
                throughput_rows_per_second=(
                    sum(value.row_count for value in values) / total_ms * 1000 if total_ms else 0
                ),
                error_rate=sum(value.error_code is not None for value in values) / len(values),
                empty_rate=sum(value.row_count == 0 for value in values) / len(values),
            )
        )
    return tuple(result)


def _percentile(values: list[float], percentile: int) -> float:
    if len(values) == 1:
        return values[0]
    return quantiles(values, n=100, method="inclusive")[percentile - 1]


__all__ = ["benchmark_sources"]
