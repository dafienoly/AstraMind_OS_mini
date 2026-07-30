"""Protected boundary checks before any fold statistic is computed."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..feature_processing import (
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
)
from ..labels import CoreForwardReturnLabelBatch, CoreLabelHorizon
from .models import CoreSelectionSpec
from .plan import CoreSelectionFold, CoreSelectionPlan
from .priors import (
    STAGE_P_PRIORS_CONTENT_HASH,
    STAGE_P_TOKENIZER_RULES_HASH,
    CoreSelectionPriorEntry,
    CoreSelectionPriorManifest,
    load_core_selection_prior_manifest,
)


@dataclass(frozen=True)
class ValidatedSelectionInputs:
    panel: CoreProcessedFeaturePanelManifest
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...]
    labels: tuple[CoreForwardReturnLabelBatch, ...]
    plan: CoreSelectionPlan
    fold: CoreSelectionFold
    horizon: CoreLabelHorizon
    prior_entries: tuple[CoreSelectionPriorEntry, ...]
    prior: CoreSelectionPriorManifest
    spec: CoreSelectionSpec


def validate_selection_inputs(
    *,
    panel_manifest: CoreProcessedFeaturePanelManifest,
    processed_envelopes: Sequence[CoreProcessedFeatureEnvelope],
    label_batches: Sequence[CoreForwardReturnLabelBatch],
    selection_plan: CoreSelectionPlan,
    fold: CoreSelectionFold,
    horizon: CoreLabelHorizon,
    prior_manifest: CoreSelectionPriorManifest | None,
    spec: CoreSelectionSpec,
) -> ValidatedSelectionInputs:
    panel_manifest = CoreProcessedFeaturePanelManifest.model_validate(
        panel_manifest.model_dump()
    )
    envelopes = tuple(
        CoreProcessedFeatureEnvelope.model_validate(item.model_dump())
        for item in processed_envelopes
    )
    labels = tuple(
        CoreForwardReturnLabelBatch.model_validate(item.model_dump())
        for item in label_batches
    )
    selection_plan = CoreSelectionPlan.model_validate(selection_plan.model_dump())
    fold = CoreSelectionFold.model_validate(fold.model_dump())
    spec = CoreSelectionSpec.model_validate(spec.model_dump())
    if horizon not in spec.allowed_horizons:
        raise ValueError("D1/D3/D5 diagnostics cannot influence H20/H60 selection")
    canonical_prior = load_core_selection_prior_manifest()
    prior = CoreSelectionPriorManifest.model_validate(
        (prior_manifest or canonical_prior).model_dump(by_alias=True)
    )
    if (
        prior != canonical_prior
        or prior.priors_content_hash != STAGE_P_PRIORS_CONTENT_HASH
        or prior.tokenizer.get("rules_hash") != STAGE_P_TOKENIZER_RULES_HASH
    ):
        raise ValueError("selection requires the exact integrated Stage P prior manifest")
    matching_folds = tuple(item for item in selection_plan.folds if item.fold_id == fold.fold_id)
    if len(matching_folds) != 1 or matching_folds[0] != fold:
        raise ValueError("selection fold must be an exact unique member of the selection plan")
    _validate_daily_alignment(
        panel_manifest,
        envelopes,
        labels,
        fold,
        horizon,
    )
    prior_entries = _validate_prior_binding(prior, panel_manifest, envelopes)
    return ValidatedSelectionInputs(
        panel=panel_manifest,
        envelopes=envelopes,
        labels=labels,
        plan=selection_plan,
        fold=fold,
        horizon=horizon,
        prior_entries=prior_entries,
        prior=prior,
        spec=spec,
    )


def _validate_daily_alignment(
    panel_manifest: CoreProcessedFeaturePanelManifest,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
    labels: tuple[CoreForwardReturnLabelBatch, ...],
    fold: CoreSelectionFold,
    horizon: CoreLabelHorizon,
) -> None:
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


def _validate_prior_binding(
    prior: CoreSelectionPriorManifest,
    panel_manifest: CoreProcessedFeaturePanelManifest,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
) -> tuple[CoreSelectionPriorEntry, ...]:
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
    return prior_entries


__all__ = ["ValidatedSelectionInputs", "validate_selection_inputs"]
