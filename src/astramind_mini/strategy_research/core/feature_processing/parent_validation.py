"""Exact-parent reconstruction for daily and multi-day processed features."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..contracts import CoreInputSnapshot, CoreUniverseDecision
from ..feature_output import CoreRawFeatureEnvelope
from .control import CoreProcessingControlPanel
from .models import CoreProcessedFeatureEnvelope, CoreProcessingSpec
from .panel import (
    CoreProcessedFeaturePanelManifest,
    build_core_processed_feature_panel_manifest,
)
from .processor import process_core_raw_feature_envelope


@dataclass(frozen=True)
class CoreProcessedFeatureEnvelopeParents:
    """All immutable inputs required to reproduce one processed daily envelope."""

    core_input: CoreInputSnapshot
    universe_rows: tuple[CoreUniverseDecision, ...]
    raw_envelope: CoreRawFeatureEnvelope
    control_panel: CoreProcessingControlPanel
    processing_spec: CoreProcessingSpec

    @classmethod
    def freeze(
        cls,
        *,
        core_input: CoreInputSnapshot,
        universe_rows: Sequence[CoreUniverseDecision],
        raw_envelope: CoreRawFeatureEnvelope,
        control_panel: CoreProcessingControlPanel,
        processing_spec: CoreProcessingSpec | None = None,
    ) -> CoreProcessedFeatureEnvelopeParents:
        return cls(
            core_input=core_input,
            universe_rows=tuple(universe_rows),
            raw_envelope=raw_envelope,
            control_panel=control_panel,
            processing_spec=processing_spec or CoreProcessingSpec(),
        )


@dataclass(frozen=True)
class CoreProcessedFeaturePanelParents:
    """Ordered daily parent bundles required to reproduce one processed panel."""

    daily_parents: tuple[CoreProcessedFeatureEnvelopeParents, ...]

    @classmethod
    def freeze(
        cls,
        daily_parents: Sequence[CoreProcessedFeatureEnvelopeParents],
    ) -> CoreProcessedFeaturePanelParents:
        return cls(daily_parents=tuple(daily_parents))


def rebuild_core_processed_feature_envelope(
    parents: CoreProcessedFeatureEnvelopeParents,
) -> CoreProcessedFeatureEnvelope:
    """Re-run the sole processing implementation over canonical parent bytes."""
    core_input, universe, raw, controls, spec = _canonical_daily_parents(parents)
    return process_core_raw_feature_envelope(
        core_input=core_input,
        universe_rows=universe,
        raw_envelope=raw,
        control_panel=controls,
        spec=spec,
    )


def validate_core_processed_feature_envelope(
    candidate: CoreProcessedFeatureEnvelope,
    parents: CoreProcessedFeatureEnvelopeParents,
) -> CoreProcessedFeatureEnvelope:
    """Reject a self-rehashed processed envelope not reproduced from raw parents."""
    expected = rebuild_core_processed_feature_envelope(parents)
    _require_same_canonical_bytes(
        candidate,
        expected,
        model=CoreProcessedFeatureEnvelope,
        message="processed envelope differs from exact processing parents",
    )
    return expected


def rebuild_core_processed_feature_panel(
    parents: CoreProcessedFeaturePanelParents,
) -> CoreProcessedFeaturePanelManifest:
    """Rebuild every daily envelope before freezing the ordered panel identity."""
    panel, _ = _rebuild_panel_bundle(parents)
    return panel


def validate_core_processed_feature_panel(
    candidate: CoreProcessedFeaturePanelManifest,
    parents: CoreProcessedFeaturePanelParents,
) -> CoreProcessedFeaturePanelManifest:
    """Reject a panel whose complete daily processing lineage cannot be rebuilt."""
    expected, _ = _rebuild_panel_bundle(parents)
    _require_same_canonical_bytes(
        candidate,
        expected,
        model=CoreProcessedFeaturePanelManifest,
        message="processed panel differs from exact daily parents",
    )
    return expected


def _rebuild_panel_bundle(
    parents: CoreProcessedFeaturePanelParents,
) -> tuple[CoreProcessedFeaturePanelManifest, tuple[CoreProcessedFeatureEnvelope, ...]]:
    if not parents.daily_parents:
        raise ValueError("processed panel parents cannot be empty")
    bundles = tuple(_canonical_daily_parents(item) for item in parents.daily_parents)
    dates = tuple(item[0].decision_date for item in bundles)
    if dates != tuple(sorted(set(dates))):
        raise ValueError("processed panel parents must be unique and date ordered")
    envelopes = tuple(
        process_core_raw_feature_envelope(
            core_input=core_input,
            universe_rows=universe,
            raw_envelope=raw,
            control_panel=controls,
            spec=spec,
        )
        for core_input, universe, raw, controls, spec in bundles
    )
    panel = build_core_processed_feature_panel_manifest(
        core_inputs=tuple(item[0] for item in bundles),
        raw_envelopes=tuple(item[2] for item in bundles),
        processed_envelopes=envelopes,
        control_panels=tuple(item[3] for item in bundles),
    )
    return panel, envelopes


def _canonical_daily_parents(
    parents: CoreProcessedFeatureEnvelopeParents,
) -> tuple[
    CoreInputSnapshot,
    tuple[CoreUniverseDecision, ...],
    CoreRawFeatureEnvelope,
    CoreProcessingControlPanel,
    CoreProcessingSpec,
]:
    core_input = CoreInputSnapshot.model_validate_json(
        CoreInputSnapshot.__pydantic_serializer__.to_json(parents.core_input)
    )
    universe = tuple(
        CoreUniverseDecision.model_validate_json(
            CoreUniverseDecision.__pydantic_serializer__.to_json(item)
        )
        for item in parents.universe_rows
    )
    raw = CoreRawFeatureEnvelope.model_validate_json(
        CoreRawFeatureEnvelope.__pydantic_serializer__.to_json(parents.raw_envelope)
    )
    controls = CoreProcessingControlPanel.model_validate_json(
        CoreProcessingControlPanel.__pydantic_serializer__.to_json(parents.control_panel)
    )
    spec = CoreProcessingSpec.model_validate_json(
        CoreProcessingSpec.__pydantic_serializer__.to_json(parents.processing_spec)
    )
    return core_input, universe, raw, controls, spec


def _require_same_canonical_bytes(
    candidate: object,
    expected: object,
    *,
    model: type[CoreProcessedFeatureEnvelope] | type[CoreProcessedFeaturePanelManifest],
    message: str,
) -> None:
    if not isinstance(candidate, model):
        raise TypeError("processed parent boundaries accept only declared contract models")
    serializer = model.__pydantic_serializer__
    candidate_bytes = serializer.to_json(candidate)
    model.model_validate_json(candidate_bytes)
    if candidate_bytes != serializer.to_json(expected):
        raise ValueError(message)


__all__ = [
    "CoreProcessedFeatureEnvelopeParents",
    "CoreProcessedFeaturePanelParents",
    "rebuild_core_processed_feature_envelope",
    "rebuild_core_processed_feature_panel",
    "validate_core_processed_feature_envelope",
    "validate_core_processed_feature_panel",
]
