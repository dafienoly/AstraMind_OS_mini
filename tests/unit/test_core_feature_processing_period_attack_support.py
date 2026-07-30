"""Fully rehashed processing attacks for later-period projection tests."""

from __future__ import annotations

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_processing import (
    CoreFrozenFeatureDefinition,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreImputationSource,
    FeatureAvailabilityState,
)


def value_attack(envelope: CoreProcessedFeatureEnvelope) -> CoreProcessedFeatureEnvelope:
    data = envelope.model_dump()
    rows = list(data["rows"])
    rows[0] = {
        **rows[0],
        "value_raw": 999.0,
        "value_winsorized": 999.0,
        "value_standardized_observed": 999.0,
        "model_value": 999.0,
    }
    data["rows"] = tuple(rows)
    return rehash_envelope(data)


def state_attack(envelope: CoreProcessedFeatureEnvelope) -> CoreProcessedFeatureEnvelope:
    data = envelope.model_dump()
    rows = list(data["rows"])
    position = next(
        index
        for index, item in enumerate(rows)
        if item["feature_id"] == envelope.feature_order[0] and item["is_missing"]
    )
    rows[position] = {
        **rows[position],
        "availability_state": FeatureAvailabilityState.NOT_APPLICABLE,
        "imputation_source": CoreImputationSource.U0_MEDIAN,
        "is_missing": False,
        "is_not_applicable": True,
    }
    data["rows"] = tuple(rows)
    sections = list(data["cross_sections"])
    sections[0] = {
        **sections[0],
        "missing_count": sections[0]["missing_count"] - 1,
        "not_applicable_count": sections[0]["not_applicable_count"] + 1,
        "applicable_count": sections[0]["applicable_count"] - 1,
        "coverage": 1.0,
    }
    data["cross_sections"] = tuple(sections)
    return rehash_envelope(data)


def row_order_attack(
    envelope: CoreProcessedFeatureEnvelope,
) -> CoreProcessedFeatureEnvelope:
    data = envelope.model_dump()
    order = (
        envelope.instrument_order[1],
        envelope.instrument_order[0],
        *envelope.instrument_order[2:],
    )
    rows_by_instrument = {
        instrument: tuple(item for item in data["rows"] if item["instrument_id"] == instrument)
        for instrument in order
    }
    data["instrument_order"] = order
    data["rows"] = tuple(item for instrument in order for item in rows_by_instrument[instrument])
    return rehash_envelope(data)


def rehash_envelope(data: dict[str, object]) -> CoreProcessedFeatureEnvelope:
    body = {key: value for key, value in data.items() if key not in {"envelope_id", "content_hash"}}
    content_hash = research_hash({"schema": "core-processed-feature-envelope-v1", **body})
    data["envelope_id"] = f"core-processed:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return CoreProcessedFeatureEnvelope.model_validate(data)


def rehash_panel(data: dict[str, object]) -> CoreProcessedFeaturePanelManifest:
    body = {
        key: value
        for key, value in data.items()
        if key not in {"panel_manifest_id", "content_hash"}
    }
    content_hash = research_hash({"schema": "core-processed-feature-panel-v1", **body})
    data["panel_manifest_id"] = f"core-processed-panel:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return CoreProcessedFeaturePanelManifest.model_validate(data)


def rehash_definition(data: dict[str, object]) -> CoreFrozenFeatureDefinition:
    body = {
        key: value for key, value in data.items() if key not in {"definition_id", "content_hash"}
    }
    content_hash = research_hash({"schema": "core-frozen-feature-definition-v1", **body})
    data["definition_id"] = f"core-frozen-feature-definition:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return CoreFrozenFeatureDefinition.model_validate(data)


def columns(feature_id: str) -> tuple[str, str, str]:
    return (
        f"{feature_id}__value",
        f"{feature_id}__is_missing",
        f"{feature_id}__is_not_applicable",
    )


__all__ = [
    "columns",
    "rehash_definition",
    "rehash_envelope",
    "rehash_panel",
    "row_order_attack",
    "state_attack",
    "value_attack",
]
