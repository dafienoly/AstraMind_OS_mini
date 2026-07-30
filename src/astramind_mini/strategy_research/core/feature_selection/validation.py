"""Protected boundary checks before any fold statistic is computed."""

from __future__ import annotations

from collections.abc import Sequence

from ..feature_processing import (
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
)
from ..labels import CoreForwardReturnLabelBatch, CoreLabelHorizon
from .models import CoreSelectionSpec
from .plan import CoreSelectionFold
from .priors import (
    STAGE_P_PRIORS_CONTENT_HASH,
    CoreSelectionPriorEntry,
    CoreSelectionPriorManifest,
    load_core_selection_prior_manifest,
)


def validate_selection_inputs(
    *,
    panel_manifest: CoreProcessedFeaturePanelManifest,
    processed_envelopes: Sequence[CoreProcessedFeatureEnvelope],
    label_batches: Sequence[CoreForwardReturnLabelBatch],
    fold: CoreSelectionFold,
    horizon: CoreLabelHorizon,
    prior_manifest: CoreSelectionPriorManifest | None,
    spec: CoreSelectionSpec,
) -> tuple[
    tuple[CoreProcessedFeatureEnvelope, ...],
    tuple[CoreForwardReturnLabelBatch, ...],
    tuple[CoreSelectionPriorEntry, ...],
    CoreSelectionPriorManifest,
]:
    if horizon not in spec.allowed_horizons:
        raise ValueError("D1/D3/D5 diagnostics cannot influence H20/H60 selection")
    prior = prior_manifest or load_core_selection_prior_manifest()
    if prior.priors_content_hash != STAGE_P_PRIORS_CONTENT_HASH:
        raise ValueError("selection requires the integrated immutable Stage P prior")
    envelopes = tuple(sorted(processed_envelopes, key=lambda item: item.decision_date))
    labels = tuple(sorted(label_batches, key=lambda item: item.decision_date))
    if (
        panel_manifest.decision_dates != fold.decision_dates
        or tuple(item.decision_date for item in envelopes) != fold.decision_dates
        or tuple(item.decision_date for item in labels) != fold.decision_dates
    ):
        raise ValueError("selection fold, panel, processed days and labels must exactly match")
    if any(
        item.package_id != panel_manifest.package_id
        or item.feature_order != panel_manifest.feature_order
        for item in envelopes
    ):
        raise ValueError("processed envelopes changed package or canonical order")
    entries_by_date = {item.decision_date: item for item in panel_manifest.entries}
    for envelope, label in zip(envelopes, labels, strict=True):
        panel_entry = entries_by_date[envelope.decision_date]
        if (
            panel_entry.processed_envelope_id != envelope.envelope_id
            or panel_entry.processed_envelope_content_hash != envelope.content_hash
            or panel_entry.universe_content_hash != envelope.universe_content_hash
        ):
            raise ValueError("processed envelope does not match panel manifest")
        if (
            not label.matured
            or label.spec.horizon != horizon
            or label.label_available_cutoff > fold.label_maturity_cutoff
            or label.label_data_snapshot_as_of > fold.label_maturity_cutoff
        ):
            raise ValueError("selection labels are wrong-horizon, immature, or cross cutoff")
        if (
            label.decision_universe_content_hash != panel_entry.universe_content_hash
            or label.research_member_ids != envelope.instrument_order
        ):
            raise ValueError("label, processed panel and control U0 must exactly match")
    prior_entries = prior.package_entries(panel_manifest.package_id)
    if tuple(item.feature_id for item in prior_entries) != panel_manifest.feature_order:
        raise ValueError("frozen prior does not match package canonical order")
    binding = prior.package_bindings.get(panel_manifest.package_id)
    if binding is None:
        raise ValueError("frozen prior lacks the processed package binding")
    for envelope in envelopes:
        if (
            envelope.definition_registry_hash != binding["required_definition_registry_hash"]
            or envelope.computation_manifest_hash != binding["computation_manifest_hash"]
        ):
            raise ValueError("processed package identity differs from frozen Stage P prior")
    versions = {(row.feature_id, row.feature_definition_version) for row in envelopes[0].rows}
    if any((item.feature_id, item.definition_version) not in versions for item in prior_entries):
        raise ValueError("processed definition versions differ from frozen prior")
    return envelopes, labels, prior_entries, prior


__all__ = ["validate_selection_inputs"]
