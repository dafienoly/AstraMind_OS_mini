"""Exact daily processed-panel lineage validation for model views."""

from __future__ import annotations

from .models import CoreProcessedFeatureEnvelope
from .panel import CoreProcessedFeaturePanelManifest


def validate_view_panel_envelopes(
    panel: CoreProcessedFeaturePanelManifest,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
) -> None:
    actual = tuple(
        (
            item.decision_date,
            item.envelope_id,
            item.content_hash,
            item.universe_content_hash,
        )
        for item in envelopes
    )
    expected = tuple(
        (
            item.decision_date,
            item.processed_envelope_id,
            item.processed_envelope_content_hash,
            item.universe_content_hash,
        )
        for item in panel.entries
    )
    if actual != expected:
        raise ValueError("feature view envelopes do not match panel entries")
    if any(
        item.package_id != panel.package_id or item.feature_order != panel.feature_order
        for item in envelopes
    ):
        raise ValueError("feature view envelope package or feature order differs from panel")


__all__ = ["validate_view_panel_envelopes"]
