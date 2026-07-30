"""Canonical identity construction for a completed within-package selection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ...application.identity import research_hash
from ..feature_processing import CoreProcessedFeaturePanelManifest
from ..labels import CoreForwardReturnLabelBatch, CoreLabelHorizon
from .models import (
    CoreFeatureSelectionEvidence,
    CoreFeatureSelectionManifest,
    CoreLabelBatchReference,
    CorePairCorrelationEvidence,
    CoreProcessedDayReference,
    CoreSelectionCluster,
    CoreSelectionReason,
    CoreSelectionSpec,
)
from .plan import CoreSelectionFold


def _freeze_selection_manifest(
    *,
    panel: CoreProcessedFeaturePanelManifest,
    labels: Sequence[CoreForwardReturnLabelBatch],
    fold: CoreSelectionFold,
    horizon: CoreLabelHorizon,
    prior_content_hash: str,
    spec: CoreSelectionSpec,
    evidence: tuple[CoreFeatureSelectionEvidence, ...],
    correlations: tuple[CorePairCorrelationEvidence, ...],
    clusters: tuple[CoreSelectionCluster, ...],
) -> CoreFeatureSelectionManifest:
    label_refs = tuple(
        CoreLabelBatchReference(
            decision_date=item.decision_date,
            batch_id=item.batch_id,
            content_hash=item.content_hash,
            universe_content_hash=item.decision_universe_content_hash,
        )
        for item in labels
    )
    processed_refs = tuple(
        CoreProcessedDayReference(
            decision_date=item.decision_date,
            processed_envelope_id=item.processed_envelope_id,
            processed_envelope_content_hash=item.processed_envelope_content_hash,
            universe_content_hash=item.universe_content_hash,
        )
        for item in panel.entries
    )
    selected = tuple(item for item in evidence if item.reason_code == CoreSelectionReason.SELECTED)
    payload = {
        "package_id": panel.package_id,
        "horizon": horizon,
        "fold": fold,
        "panel_manifest_id": panel.panel_manifest_id,
        "panel_content_hash": panel.content_hash,
        "prior_content_hash": prior_content_hash,
        "selection_spec": spec,
        "selection_spec_hash": research_hash(spec),
        "processed_days": processed_refs,
        "label_batches": label_refs,
        "feature_order": panel.feature_order,
        "feature_evidence": evidence,
        "pair_correlations": correlations,
        "clusters": clusters,
        "selected_feature_keys": tuple(item.feature_key for item in selected),
        "selected_feature_ids": tuple(item.feature_id for item in selected),
    }
    manifest_data: dict[str, Any] = dict(payload)
    draft = CoreFeatureSelectionManifest.model_construct(
        manifest_id="pending-selection-identity",
        content_hash="sha256:" + "0" * 64,
        **manifest_data,
    )
    content_hash = research_hash(
        {
            "schema": "core-feature-selection-manifest-v1",
            **{
                key: value
                for key, value in draft.model_dump().items()
                if key not in {"manifest_id", "content_hash"}
            },
        }
    )
    return CoreFeatureSelectionManifest.model_validate(
        {
            "manifest_id": f"core-selection:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **manifest_data,
        }
    )


__all__: list[str] = []
