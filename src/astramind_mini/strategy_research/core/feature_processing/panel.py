"""Ordered multi-day processed panel identity."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier

from ...application.identity import research_hash
from ..contracts import CoreInputSnapshot
from ..feature_output import CoreRawFeatureEnvelope
from .control import CoreProcessingControlPanel
from .models import CoreProcessedFeatureEnvelope


class CoreProcessedFeaturePanelEntry(ContractModel):
    decision_date: date
    core_input_snapshot_id: Identifier
    core_input_content_hash: ContentHash
    raw_envelope_id: Identifier
    raw_envelope_content_hash: ContentHash
    processed_envelope_id: Identifier
    processed_envelope_content_hash: ContentHash
    universe_content_hash: ContentHash
    control_panel_id: Identifier
    control_panel_content_hash: ContentHash


class CoreProcessedFeaturePanelManifest(ContractModel):
    panel_manifest_id: Identifier
    content_hash: ContentHash
    package_id: Identifier
    feature_order: tuple[Identifier, ...] = Field(min_length=1)
    entries: tuple[CoreProcessedFeaturePanelEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> CoreProcessedFeaturePanelManifest:
        if len(set(self.feature_order)) != len(self.feature_order):
            raise ValueError("processed panel feature order must be unique")
        dates = tuple(item.decision_date for item in self.entries)
        if dates != tuple(sorted(set(dates))):
            raise ValueError("processed panel dates must be unique and ascending")
        expected_hash = research_hash(
            {
                "schema": "core-processed-feature-panel-v1",
                "package_id": self.package_id,
                "feature_order": self.feature_order,
                "entries": self.entries,
            }
        )
        expected_id = f"core-processed-panel:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.panel_manifest_id != expected_id:
            raise ValueError("processed panel canonical identity mismatch")
        return self

    @property
    def decision_dates(self) -> tuple[date, ...]:
        return tuple(item.decision_date for item in self.entries)


def build_core_processed_feature_panel_manifest(
    *,
    core_inputs: Sequence[CoreInputSnapshot],
    raw_envelopes: Sequence[CoreRawFeatureEnvelope],
    processed_envelopes: Sequence[CoreProcessedFeatureEnvelope],
    control_panels: Sequence[CoreProcessingControlPanel],
) -> CoreProcessedFeaturePanelManifest:
    """Bind every date's complete immutable lineage before cross-day statistics."""
    if not (
        len(core_inputs)
        == len(raw_envelopes)
        == len(processed_envelopes)
        == len(control_panels)
        > 0
    ):
        raise ValueError("panel lineage sequences must be non-empty and equal length")
    bundles = sorted(
        zip(
            core_inputs,
            raw_envelopes,
            processed_envelopes,
            control_panels,
            strict=True,
        ),
        key=lambda item: item[0].decision_date,
    )
    package_id = bundles[0][2].package_id
    feature_order = bundles[0][2].feature_order
    entries = tuple(
        _panel_entry(
            core_input=core_input,
            raw=raw,
            processed=processed,
            controls=controls,
            package_id=package_id,
            feature_order=feature_order,
        )
        for core_input, raw, processed, controls in bundles
    )
    payload = {
        "schema": "core-processed-feature-panel-v1",
        "package_id": package_id,
        "feature_order": feature_order,
        "entries": entries,
    }
    content_hash = research_hash(payload)
    return CoreProcessedFeaturePanelManifest(
        panel_manifest_id=(f"core-processed-panel:{content_hash.removeprefix('sha256:')}"),
        content_hash=content_hash,
        package_id=package_id,
        feature_order=feature_order,
        entries=entries,
    )


def _panel_entry(
    *,
    core_input: CoreInputSnapshot,
    raw: CoreRawFeatureEnvelope,
    processed: CoreProcessedFeatureEnvelope,
    controls: CoreProcessingControlPanel,
    package_id: str,
    feature_order: tuple[str, ...],
) -> CoreProcessedFeaturePanelEntry:
    if (
        core_input.decision_date != processed.decision_date
        or raw.feature_snapshot.as_of != core_input.cutoff_at
        or controls.decision_date != core_input.decision_date
    ):
        raise ValueError("daily panel bundle date mismatch")
    if (
        processed.core_input_snapshot_id != core_input.core_input_snapshot_id
        or processed.core_input_content_hash != core_input.content_hash
        or processed.raw_feature_snapshot_id != raw.feature_snapshot.feature_snapshot_id
        or processed.raw_feature_content_hash != raw.feature_snapshot.content_hash
        or processed.raw_manifest_id != raw.manifest.manifest_id
        or processed.raw_manifest_content_hash != raw.manifest.content_hash
        or processed.control_panel_id != controls.panel_id
        or processed.control_panel_content_hash != controls.content_hash
    ):
        raise ValueError("daily panel bundle identity mismatch")
    if (
        processed.package_id != package_id
        or processed.feature_order != feature_order
        or processed.universe_content_hash != core_input.universe_content_hash
        or controls.universe_content_hash != core_input.universe_content_hash
    ):
        raise ValueError("daily panel package, order, or U0 mismatch")
    return CoreProcessedFeaturePanelEntry(
        decision_date=core_input.decision_date,
        core_input_snapshot_id=core_input.core_input_snapshot_id,
        core_input_content_hash=core_input.content_hash,
        raw_envelope_id=raw.feature_snapshot.feature_snapshot_id,
        raw_envelope_content_hash=raw.feature_snapshot.content_hash,
        processed_envelope_id=processed.envelope_id,
        processed_envelope_content_hash=processed.content_hash,
        universe_content_hash=core_input.universe_content_hash,
        control_panel_id=controls.panel_id,
        control_panel_content_hash=controls.content_hash,
    )


__all__ = [
    "CoreProcessedFeaturePanelEntry",
    "CoreProcessedFeaturePanelManifest",
    "build_core_processed_feature_panel_manifest",
]
