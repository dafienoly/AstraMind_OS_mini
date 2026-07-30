"""Canonical identity helpers for raw core feature artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from astramind_mini.contracts.base import ContentHash

from ..application.identity import research_hash
from .contracts import CoreFeaturePackageSpec
from .feature_values import FeatureAvailabilityState

RAW_OUTPUT_SCHEMA = "core-raw-feature-output-v2"
DEFINITION_REGISTRY_SCHEMA = "core-raw-feature-output-v1"


class DefinitionRow(Protocol):
    feature_definition_id: str
    feature_definition_version: str


class RawValueRow(DefinitionRow, Protocol):
    instrument_id: str
    decision_time: datetime
    value_raw: float | None
    availability_state: FeatureAvailabilityState
    missing_reason_code: str | None


def canonical_package_spec_hash(package_spec: CoreFeaturePackageSpec) -> str:
    return research_hash(package_spec.model_dump(mode="json"))


def canonical_definition_registry(
    feature_order: Sequence[str],
    rows: Sequence[DefinitionRow],
) -> tuple[tuple[int, str, str], ...]:
    registry = []
    for ordinal, feature_id in enumerate(feature_order):
        versions = {
            item.feature_definition_version
            for item in rows
            if item.feature_definition_id == feature_id
        }
        if len(versions) != 1:
            raise ValueError("each ordered feature must have exactly one definition version")
        registry.append((ordinal, feature_id, versions.pop()))
    return tuple(registry)


def canonical_definition_registry_hash(
    feature_order: Sequence[str],
    rows: Sequence[DefinitionRow],
) -> str:
    return research_hash(
        {
            "schema": DEFINITION_REGISTRY_SCHEMA,
            "definitions": canonical_definition_registry(feature_order, rows),
        }
    )


def validated_definition_registry_hash(
    package_spec: CoreFeaturePackageSpec,
    feature_order: Sequence[str],
    rows: Sequence[DefinitionRow],
) -> str:
    registry_hash = canonical_definition_registry_hash(feature_order, rows)
    if registry_hash != package_spec.required_definition_registry_hash:
        raise ValueError("definition registry does not match the canonical package")
    return registry_hash


def canonical_raw_row_hash(row: RawValueRow) -> str:
    return research_hash(
        {
            "instrument_id": row.instrument_id,
            "decision_time": row.decision_time,
            "feature_definition_id": row.feature_definition_id,
            "feature_definition_version": row.feature_definition_version,
            "value_raw": row.value_raw,
            "availability_state": row.availability_state,
            "missing_reason_code": row.missing_reason_code,
        }
    )


def canonical_row_content_hashes(rows: Sequence[RawValueRow]) -> tuple[str, ...]:
    return tuple(canonical_raw_row_hash(item) for item in rows)


def canonical_rows_content_hash(row_content_hashes: Sequence[ContentHash | str]) -> str:
    return research_hash(
        {
            "schema": RAW_OUTPUT_SCHEMA,
            "row_content_hashes": tuple(row_content_hashes),
        }
    )


def canonical_raw_snapshot_content_hash(
    *,
    core_input_snapshot_id: str,
    core_input_content_hash: str,
    data_snapshot_id: str,
    decision_time: datetime,
    package_spec_hash: str,
    definition_registry_hash: str,
    computation_manifest_hash: str,
    feature_order: Sequence[str],
    rows_content_hash: str,
) -> str:
    return research_hash(
        {
            "schema": RAW_OUTPUT_SCHEMA,
            "core_input_snapshot_id": core_input_snapshot_id,
            "core_input_content_hash": core_input_content_hash,
            "data_snapshot_id": data_snapshot_id,
            "decision_time": decision_time,
            "package_spec_hash": package_spec_hash,
            "definition_registry_hash": definition_registry_hash,
            "computation_manifest_hash": computation_manifest_hash,
            "feature_order": tuple(feature_order),
            "rows_content_hash": rows_content_hash,
        }
    )


def canonical_feature_snapshot_id(content_hash: str) -> str:
    return f"feature-snapshot:{content_hash.removeprefix('sha256:')}"


def canonical_manifest_content_hash(
    *,
    rows_content_hash: str,
    row_content_hashes: Sequence[str],
    feature_snapshot_id: str,
    core_input_snapshot_id: str,
    core_input_content_hash: str,
    package_spec_hash: str,
    definition_registry_hash: str,
    computation_manifest_hash: str,
    package_id: str,
    feature_order: Sequence[str],
    row_order: Sequence[object],
    feature_coverage: Sequence[object],
    row_count: int,
    instrument_count: int,
    observed_count: int,
    missing_count: int,
    not_applicable_count: int,
    observed_coverage_ratio: float,
) -> str:
    return research_hash(
        {
            "schema": RAW_OUTPUT_SCHEMA,
            "rows_content_hash": rows_content_hash,
            "row_content_hashes": tuple(row_content_hashes),
            "feature_snapshot_id": feature_snapshot_id,
            "core_input_snapshot_id": core_input_snapshot_id,
            "core_input_content_hash": core_input_content_hash,
            "package_spec_hash": package_spec_hash,
            "definition_registry_hash": definition_registry_hash,
            "computation_manifest_hash": computation_manifest_hash,
            "package_id": package_id,
            "feature_order": tuple(feature_order),
            "row_order": tuple(row_order),
            "feature_coverage": tuple(feature_coverage),
            "row_count": row_count,
            "instrument_count": instrument_count,
            "observed_count": observed_count,
            "missing_count": missing_count,
            "not_applicable_count": not_applicable_count,
            "observed_coverage_ratio": observed_coverage_ratio,
        }
    )


def canonical_manifest_id(content_hash: str) -> str:
    return f"core-raw-feature-manifest:{content_hash.removeprefix('sha256:')}"


__all__ = [
    "DEFINITION_REGISTRY_SCHEMA",
    "RAW_OUTPUT_SCHEMA",
    "canonical_definition_registry",
    "canonical_definition_registry_hash",
    "canonical_feature_snapshot_id",
    "canonical_manifest_content_hash",
    "canonical_manifest_id",
    "canonical_package_spec_hash",
    "canonical_raw_row_hash",
    "canonical_raw_snapshot_content_hash",
    "canonical_row_content_hashes",
    "canonical_rows_content_hash",
    "validated_definition_registry_hash",
]
