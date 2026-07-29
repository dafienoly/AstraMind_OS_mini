"""Provider-neutral contracts for routed dataset acquisition."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)


class SourceHealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"
    UNSUPPORTED = "unsupported"


class CanonicalDatasetRequest(ContractModel):
    dataset_name: Identifier
    as_of: AwareDatetime
    start_date: date | None = None
    end_date: date | None = None
    universe: tuple[Identifier, ...] = ()
    fields: tuple[Identifier, ...] = ()
    filters: dict[str, str | int | bool | tuple[str, ...]] = Field(default_factory=dict)
    allow_empty: bool = False
    frequency: str = "1d"
    adjustment: str = "none"
    point_in_time_policy: Version = "provider-announcement-time-v1"


class ProviderBatch(ContractModel):
    provider_id: Identifier
    provider_version: Version
    native_interface: Identifier
    source_endpoint: Identifier
    request_identity: ContentHash
    retrieved_at: AwareDatetime
    rows: tuple[dict[str, object], ...]
    raw_payload: object
    completeness: float = Field(ge=0, le=1)
    known_gaps: tuple[str, ...] = ()
    latency_breakdown_ms: dict[str, float] = Field(default_factory=dict)


class SourceProviderEpoch(ContractModel):
    provider: Identifier
    effective_from: date
    effective_to: date | None = None


class DatasetSourceRoute(ContractModel):
    dataset_name: Identifier
    providers: tuple[Identifier, ...] = Field(min_length=1)
    adapter_version: Version
    quality_gate_version: Version
    timeout_seconds: float = Field(gt=0, le=600)
    required_fields: tuple[Identifier, ...] = ()
    primary_key: tuple[Identifier, ...] = ()
    allow_empty: bool = False
    provider_lineage: tuple[SourceProviderEpoch, ...] = ()


class SourceSelectionEvidence(ContractModel):
    dataset_name: Identifier
    route_hash: ContentHash
    selected_provider: Identifier
    attempted_providers: tuple[Identifier, ...] = Field(min_length=1)
    fallback_reason: str | None = None
    selected_request_identity: ContentHash
    selected_content_hash: ContentHash
    fetch_ms: float = Field(ge=0)
    normalize_ms: float = Field(default=0, ge=0)
    persist_ms: float = Field(default=0, ge=0)
    fallback_count: int = Field(ge=0)
    recorded_at: AwareDatetime


class BenchmarkSample(ContractModel):
    provider_id: Identifier
    dataset_name: Identifier
    scenario_id: ContentHash | str = "unspecified"
    cache_state: str
    row_count: int = Field(ge=0)
    total_ms: float = Field(ge=0)
    fetch_ms: float = Field(ge=0)
    normalize_ms: float = Field(ge=0)
    persist_ms: float = Field(ge=0)
    error_code: str | None = None


class BenchmarkStatistics(ContractModel):
    provider_id: Identifier
    dataset_name: Identifier
    scenario_id: ContentHash | str
    sample_count: int = Field(gt=0)
    p50_ms: float = Field(ge=0)
    p95_ms: float = Field(ge=0)
    p99_ms: float = Field(ge=0)
    throughput_rows_per_second: float = Field(ge=0)
    error_rate: float = Field(ge=0, le=1)
    empty_rate: float = Field(ge=0, le=1)


class BenchmarkScenario(ContractModel):
    scenario_id: ContentHash | str
    dataset_name: Identifier
    start_date: date | None = None
    end_date: date | None = None
    universe_count: int = Field(ge=0)
    frequency: str
    adjustment: str


class ProviderBenchmarkReport(ContractModel):
    benchmark_id: ContentHash
    benchmark_version: Version
    started_at: AwareDatetime
    ended_at: AwareDatetime
    environment: dict[str, str]
    scenarios: tuple[BenchmarkScenario, ...] = ()
    samples: tuple[BenchmarkSample, ...]
    statistics: tuple[BenchmarkStatistics, ...] = ()
    conclusions: dict[str, str]


class SourceHealth(ContractModel):
    provider_id: Identifier
    provider_version: Version
    state: SourceHealthState
    checked_at: AwareDatetime
    latency_ms: float | None = Field(default=None, ge=0)
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "BenchmarkSample",
    "BenchmarkScenario",
    "BenchmarkStatistics",
    "CanonicalDatasetRequest",
    "DatasetSourceRoute",
    "ProviderBatch",
    "ProviderBenchmarkReport",
    "SourceHealth",
    "SourceHealthState",
    "SourceProviderEpoch",
    "SourceSelectionEvidence",
]
