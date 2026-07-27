"""Strict Data-context contracts for provider evidence and dataset publication."""

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


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PERMISSION_DENIED = "permission_denied"
    EMPTY = "empty"
    STALE = "stale"
    ERROR = "error"
    NOT_PROBED = "not_probed"


class RawRecordEnvelope(ContractModel):
    provider: Identifier
    interface_name: Identifier
    source_endpoint: Identifier
    request_identity: ContentHash
    market_time: AwareDatetime | None = None
    received_at: AwareDatetime
    schema_version: Version
    content_hash: ContentHash


class DatasetManifest(ContractModel):
    dataset_name: Identifier
    dataset_version: ContentHash
    schema_version: Version
    provider: Identifier
    source_endpoint: Identifier
    request_identity: ContentHash
    retrieved_at: AwareDatetime
    market_timezone: Identifier
    date_range: tuple[date, date]
    universe: tuple[str, ...]
    primary_key: tuple[str, ...] = Field(min_length=1)
    availability_rule: str
    units: tuple[str, ...]
    content_hash: ContentHash
    row_count: int = Field(ge=0)
    known_gaps: tuple[str, ...] = ()
    critical_gaps: tuple[str, ...] = ()
    artifact_paths: tuple[str, ...] = Field(min_length=1)
    publish_status: str = Field(pattern=r"^complete$")


class ProviderCapability(ContractModel):
    capability_id: Identifier
    interface_name: Identifier
    state: CapabilityState
    interface_present: bool
    configured: bool
    permission_available: bool | None
    data_available: bool
    observed_fields: tuple[str, ...] = ()
    row_count: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    schema_fingerprint: ContentHash | None = None
    coverage_summary: str | None = None
    error_code: Identifier | None = None
    known_gaps: tuple[str, ...] = ()


class ProbeReport(ContractModel):
    probe_id: ContentHash
    provider: Identifier
    gateway_version: Version
    client_version: Version
    probed_at: AwareDatetime
    capabilities: tuple[ProviderCapability, ...] = Field(min_length=1)
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "CapabilityState",
    "DatasetManifest",
    "ProbeReport",
    "ProviderCapability",
    "RawRecordEnvelope",
]
