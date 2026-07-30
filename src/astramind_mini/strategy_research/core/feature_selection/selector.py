"""End-to-end within-package H20/H60 frozen selection."""

from __future__ import annotations

import itertools
from collections.abc import Sequence

from ..feature_processing import (
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
)
from ..labels import CoreForwardReturnLabelBatch, CoreLabelHorizon
from .bh import benjamini_hochberg
from .clustering import complete_linkage_clusters
from .feature_evidence import build_initial_feature_evidence
from .metrics import (
    correlation_distance_map,
    pair_correlation_evidence,
)
from .models import (
    CoreFeatureSelectionEvidence,
    CoreFeatureSelectionManifest,
    CoreSelectionCluster,
    CoreSelectionReason,
    CoreSelectionSpec,
)
from .plan import CoreSelectionFold
from .priors import CoreSelectionPriorEntry, CoreSelectionPriorManifest
from .selection_freeze import _freeze_selection_manifest
from .validation import validate_selection_inputs


def select_core_features(
    *,
    panel_manifest: CoreProcessedFeaturePanelManifest,
    processed_envelopes: Sequence[CoreProcessedFeatureEnvelope],
    label_batches: Sequence[CoreForwardReturnLabelBatch],
    fold: CoreSelectionFold,
    horizon: CoreLabelHorizon,
    prior_manifest: CoreSelectionPriorManifest | None = None,
    spec: CoreSelectionSpec | None = None,
) -> CoreFeatureSelectionManifest:
    """Freeze one package/horizon selection using only exact fold inputs."""
    rules = spec or CoreSelectionSpec()
    envelopes, labels, prior_entries, prior = validate_selection_inputs(
        panel_manifest=panel_manifest,
        processed_envelopes=processed_envelopes,
        label_batches=label_batches,
        fold=fold,
        horizon=horizon,
        prior_manifest=prior_manifest,
        spec=rules,
    )
    evidence = _initial_evidence(
        prior_entries=prior_entries,
        envelopes=envelopes,
        labels=labels,
        fold=fold,
        horizon=horizon,
        spec=rules,
    )
    bh_results = benjamini_hochberg(
        {
            item.feature_key: (item.bootstrap_p_value if item.selection_eligible else None)
            for item in evidence
        },
        fdr=rules.bh_fdr,
    )
    evidence = tuple(_apply_bh(item, bh_results.get(item.feature_key)) for item in evidence)
    passed = tuple(item for item in evidence if item.bh_passed)
    correlations = tuple(
        pair_correlation_evidence(
            left_feature_key=left.feature_key,
            right_feature_key=right.feature_key,
            left_feature_id=left.feature_id,
            right_feature_id=right.feature_id,
            left_envelopes=envelopes,
            right_envelopes=envelopes,
            minimum_pairs=rules.correlation_minimum_daily_pairs,
            minimum_dates=rules.correlation_minimum_valid_dates,
        )
        for left, right in itertools.combinations(passed, 2)
    )
    clusters = complete_linkage_clusters(
        tuple(item.feature_key for item in passed),
        correlation_distance_map(correlations),
        maximum_distance=rules.complete_linkage_maximum_distance,
    )
    evidence_by_key = {item.feature_key: item for item in evidence}
    frozen_clusters = tuple(
        CoreSelectionCluster(
            members=members,
            representative=min(
                members,
                key=lambda key: _representative_key(evidence_by_key[key]),
            ),
        )
        for members in clusters
    )
    selected_set = {item.representative for item in frozen_clusters}
    evidence = tuple(_apply_cluster_result(item, selected_set) for item in evidence)
    return _freeze_selection_manifest(
        panel=panel_manifest,
        labels=labels,
        fold=fold,
        horizon=horizon,
        prior_content_hash=prior.priors_content_hash,
        spec=rules,
        evidence=evidence,
        correlations=correlations,
        clusters=frozen_clusters,
    )


def _initial_evidence(
    *,
    prior_entries: Sequence[CoreSelectionPriorEntry],
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
    labels: tuple[CoreForwardReturnLabelBatch, ...],
    fold: CoreSelectionFold,
    horizon: CoreLabelHorizon,
    spec: CoreSelectionSpec,
) -> tuple[CoreFeatureSelectionEvidence, ...]:
    return tuple(
        build_initial_feature_evidence(
            prior=item,
            envelopes=envelopes,
            labels=labels,
            fold=fold,
            horizon=horizon,
            spec=spec,
        )
        for item in prior_entries
    )


def _apply_bh(
    evidence: CoreFeatureSelectionEvidence,
    result: tuple[int, float, bool] | None,
) -> CoreFeatureSelectionEvidence:
    if result is None:
        return evidence
    rank, threshold, passed = result
    data = evidence.model_dump()
    data.update(
        bh_rank=rank,
        bh_threshold=threshold,
        bh_passed=passed,
        reason_code=(
            CoreSelectionReason.CLUSTER_REDUNDANT if passed else CoreSelectionReason.BH_REJECTED
        ),
    )
    return CoreFeatureSelectionEvidence.model_validate(data)


def _representative_key(evidence: CoreFeatureSelectionEvidence) -> tuple[object, ...]:
    return (
        not evidence.direction_consistent,
        evidence.complexity,
        evidence.coverage_mean is None,
        -(evidence.coverage_mean or 0.0),
        evidence.turnover is None,
        evidence.turnover or 0.0,
        evidence.stability is None,
        -(evidence.stability or 0.0),
        evidence.feature_key,
    )


def _apply_cluster_result(
    evidence: CoreFeatureSelectionEvidence,
    selected: set[str],
) -> CoreFeatureSelectionEvidence:
    if not evidence.bh_passed:
        return evidence
    data = evidence.model_dump()
    data["reason_code"] = (
        CoreSelectionReason.SELECTED
        if evidence.feature_key in selected
        else CoreSelectionReason.CLUSTER_REDUNDANT
    )
    return CoreFeatureSelectionEvidence.model_validate(data)


__all__ = ["select_core_features"]
