"""Protected boundary checks before any fold statistic is computed."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from ..feature_processing import (
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
)
from ..labels import (
    CoreForwardReturnLabelBatch,
    CoreLabelHorizon,
)
from .models import CoreSelectionSpec
from .plan import CoreSelectionFold, CoreSelectionPlan
from .priors import (
    STAGE_P_PRIORS_CONTENT_HASH,
    STAGE_P_TOKENIZER_RULES_HASH,
    CoreSelectionPriorEntry,
    CoreSelectionPriorManifest,
    load_core_selection_prior_manifest,
)

_VALIDATED_ENVELOPE_FINGERPRINTS: OrderedDict[bytes, None] = OrderedDict()
_VALIDATED_ENVELOPE_FINGERPRINT_MAXSIZE = 4_096
_VALIDATED_LABEL_FINGERPRINTS: OrderedDict[bytes, None] = OrderedDict()
_VALIDATED_LABEL_FINGERPRINT_MAXSIZE = 4_096


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
    _revalidate_panel(panel_manifest)
    envelopes = tuple(processed_envelopes)
    for envelope in envelopes:
        _revalidate_envelope(envelope)
    labels = tuple(label_batches)
    for label in labels:
        _revalidate_label(label)
    _revalidate_plan(selection_plan, fold)
    cast(Callable[[], object], spec.validate_fixed_v1)()
    if horizon not in spec.allowed_horizons:
        raise ValueError("D1/D3/D5 diagnostics cannot influence H20/H60 selection")
    canonical_prior = load_core_selection_prior_manifest()
    prior = prior_manifest or canonical_prior
    cast(Callable[[], object], prior.validate_frozen_identity)()
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


def _revalidate_panel(panel: CoreProcessedFeaturePanelManifest) -> None:
    if not isinstance(panel, CoreProcessedFeaturePanelManifest):
        raise TypeError("selection panel must use the public frozen contract")
    cast(Callable[[], object], panel.validate_identity)()


def _revalidate_envelope(envelope: CoreProcessedFeatureEnvelope) -> None:
    if not isinstance(envelope, CoreProcessedFeatureEnvelope):
        raise TypeError("selection envelopes must use the public frozen contract")
    fingerprint = hashlib.sha256(
        CoreProcessedFeatureEnvelope.__pydantic_serializer__.to_json(envelope)
    ).digest()
    if fingerprint in _VALIDATED_ENVELOPE_FINGERPRINTS:
        _VALIDATED_ENVELOPE_FINGERPRINTS.move_to_end(fingerprint)
        return
    for row in envelope.rows:
        cast(Callable[[], object], row.validate_state)()
    for cross_section in envelope.cross_sections:
        cast(Callable[[], object], cross_section.validate_counts)()
    cast(Callable[[], object], envelope.processing_spec.validate_fixed_v1)()
    cast(Callable[[], object], envelope.validate_identity)()
    _VALIDATED_ENVELOPE_FINGERPRINTS[fingerprint] = None
    if len(_VALIDATED_ENVELOPE_FINGERPRINTS) > _VALIDATED_ENVELOPE_FINGERPRINT_MAXSIZE:
        _VALIDATED_ENVELOPE_FINGERPRINTS.popitem(last=False)


def _revalidate_label(label: CoreForwardReturnLabelBatch) -> None:
    if not isinstance(label, CoreForwardReturnLabelBatch):
        raise TypeError("selection labels must use the public frozen contract")
    fingerprint = hashlib.sha256(
        CoreForwardReturnLabelBatch.__pydantic_serializer__.to_json(label)
    ).digest()
    if fingerprint in _VALIDATED_LABEL_FINGERPRINTS:
        _VALIDATED_LABEL_FINGERPRINTS.move_to_end(fingerprint)
        return
    cast(Callable[[], object], label.spec.validate_fixed_v1)()
    cast(Callable[[], object], label.common_calendar.validate_identity)()
    for universe_row in label.universe_rows:
        cast(Callable[[], object], universe_row.validate_decision)()
    for row in label.rows:
        cast(Callable[[], object], row.validate_state)()
    cast(Callable[[], object], label.validate_identity_and_counts)()
    _VALIDATED_LABEL_FINGERPRINTS[fingerprint] = None
    if len(_VALIDATED_LABEL_FINGERPRINTS) > _VALIDATED_LABEL_FINGERPRINT_MAXSIZE:
        _VALIDATED_LABEL_FINGERPRINTS.popitem(last=False)


def _revalidate_plan(plan: CoreSelectionPlan, fold: CoreSelectionFold) -> None:
    if not isinstance(plan, CoreSelectionPlan) or not isinstance(fold, CoreSelectionFold):
        raise TypeError("selection plan and fold must use public frozen contracts")
    for item in plan.folds:
        for subfold in item.subfolds:
            cast(Callable[[], object], subfold.validate_dates)()
        cast(Callable[[], object], item.validate_identity)()
    cast(Callable[[], object], plan.validate_identity)()
    cast(Callable[[], object], fold.validate_identity)()


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
