from __future__ import annotations

import itertools
from datetime import UTC, date, datetime

from test_core_feature_processing_parent_support import (
    frozen_envelopes,
    frozen_panel,
)

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_processing import (
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
)
from astramind_mini.strategy_research.core.feature_selection import (
    STAGE_P_PRIORS_CONTENT_HASH,
    STAGE_P_TOKENIZER_RULES_HASH,
    CoreCorrelationStatus,
    CoreDailyCoverageEvidence,
    CoreDailyRankICEvidence,
    CoreFeatureSelectionEvidence,
    CoreFeatureSelectionManifest,
    CoreFoldCoverageEvidence,
    CoreLabelBatchReference,
    CorePairCorrelationEvidence,
    CoreProcessedDayReference,
    CoreSelectionCluster,
    CoreSelectionFold,
    CoreSelectionReason,
    CoreSelectionSpec,
    CoreSubfoldRankICEvidence,
    CoreTurnoverReason,
    CoreTurnoverTransitionEvidence,
    benjamini_hochberg,
    freeze_core_selection_fold,
    freeze_core_selection_plan,
    selection_seed,
)
from astramind_mini.strategy_research.core.feature_selection.coverage import (
    CoreCoverageReason,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon

MATURITY_CUTOFF = datetime(2026, 1, 1, tzinfo=UTC)


def frozen_selection(
    *,
    panel: CoreProcessedFeaturePanelManifest,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
    horizon: CoreLabelHorizon = CoreLabelHorizon.H20,
    p_values: tuple[float | None, ...] | None = None,
    coverage_passed: tuple[bool, ...] | None = None,
) -> CoreFeatureSelectionManifest:
    dates = tuple(item.decision_date for item in envelopes)
    fold = freeze_core_selection_fold(
        decision_dates=dates,
        label_maturity_cutoff=MATURITY_CUTOFF,
        subfold_dates=(dates[:60], dates[60:120], dates[120:]),
    )
    feature_count = len(panel.feature_order)
    p_values = p_values or tuple(0.01 for _ in range(feature_count))
    coverage_passed = coverage_passed or tuple(True for _ in range(feature_count))
    keys = tuple(f"{item}@1.0.0" for item in panel.feature_order)
    bh = benjamini_hochberg(
        {
            key: p_value if passed else None
            for key, p_value, passed in zip(
                keys,
                p_values,
                coverage_passed,
                strict=True,
            )
        },
        fdr=0.10,
    )
    evidence = _selection_evidence(
        panel=panel,
        dates=dates,
        fold_id=fold.fold_id,
        horizon=horizon,
        p_values=p_values,
        coverage_passed=coverage_passed,
        bh=bh,
    )
    return _freeze_selection_fixture(
        panel=panel,
        envelopes=envelopes,
        horizon=horizon,
        fold=fold,
        evidence=evidence,
    )


def _selection_evidence(
    *,
    panel: CoreProcessedFeaturePanelManifest,
    dates: tuple[date, ...],
    fold_id: str,
    horizon: CoreLabelHorizon,
    p_values: tuple[float | None, ...],
    coverage_passed: tuple[bool, ...],
    bh: dict[str, tuple[int, float, bool]],
) -> tuple[CoreFeatureSelectionEvidence, ...]:
    keys = tuple(f"{item}@1.0.0" for item in panel.feature_order)
    return tuple(
        _feature_evidence(
            feature_id=feature_id,
            feature_key=feature_key,
            dates=dates,
            fold_id=fold_id,
            horizon=horizon,
            p_value=p_value,
            coverage_passed=passed,
            bh_result=bh.get(feature_key),
            canonical_order=index,
        )
        for index, (feature_id, feature_key, p_value, passed) in enumerate(
            zip(panel.feature_order, keys, p_values, coverage_passed, strict=True),
            start=1,
        )
    )


def _freeze_selection_fixture(
    *,
    panel: CoreProcessedFeaturePanelManifest,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
    horizon: CoreLabelHorizon,
    fold: CoreSelectionFold,
    evidence: tuple[CoreFeatureSelectionEvidence, ...],
) -> CoreFeatureSelectionManifest:
    pairs, clusters, selected = _selection_relationships(evidence)
    spec = CoreSelectionSpec()
    plan = freeze_core_selection_plan((fold,))
    payload = {
        "schema": "core-feature-selection-manifest-v1",
        "package_id": panel.package_id,
        "horizon": horizon,
        "selection_plan_id": plan.plan_id,
        "selection_plan_content_hash": plan.content_hash,
        "fold": fold,
        "panel_manifest_id": panel.panel_manifest_id,
        "panel_content_hash": panel.content_hash,
        "prior_content_hash": STAGE_P_PRIORS_CONTENT_HASH,
        "prior_tokenizer_rules_hash": STAGE_P_TOKENIZER_RULES_HASH,
        "selection_spec": spec,
        "selection_spec_hash": research_hash(spec),
        "processed_days": tuple(
            CoreProcessedDayReference(
                decision_date=item.decision_date,
                processed_envelope_id=item.envelope_id,
                processed_envelope_content_hash=item.content_hash,
                universe_content_hash=item.universe_content_hash,
            )
            for item in envelopes
        ),
        "label_batches": tuple(
            CoreLabelBatchReference(
                decision_date=item.decision_date,
                batch_id=f"label-{horizon}-{index}",
                content_hash=research_hash({"label": (horizon, index)}),
                universe_content_hash=item.universe_content_hash,
            )
            for index, item in enumerate(envelopes)
        ),
        "feature_order": panel.feature_order,
        "feature_evidence": evidence,
        "pair_correlations": pairs,
        "clusters": clusters,
        "selected_feature_keys": tuple(item.feature_key for item in selected),
        "selected_feature_ids": tuple(item.feature_id for item in selected),
    }
    manifest_data = {key: value for key, value in payload.items() if key != "schema"}
    draft = CoreFeatureSelectionManifest.model_construct(
        manifest_id="pending",
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


def _selection_relationships(
    evidence: tuple[CoreFeatureSelectionEvidence, ...],
) -> tuple[
    tuple[CorePairCorrelationEvidence, ...],
    tuple[CoreSelectionCluster, ...],
    tuple[CoreFeatureSelectionEvidence, ...],
]:
    passed_evidence = tuple(item for item in evidence if item.bh_passed)
    pairs = tuple(
        CorePairCorrelationEvidence(
            left_feature_key=min(left.feature_key, right.feature_key),
            right_feature_key=max(left.feature_key, right.feature_key),
            valid_date_count=60,
            median_daily_spearman=0.0,
            distance=1.0,
            status=CoreCorrelationStatus.AVAILABLE,
        )
        for left, right in itertools.combinations(passed_evidence, 2)
    )
    clusters = tuple(
        CoreSelectionCluster(members=(item.feature_key,), representative=item.feature_key)
        for item in passed_evidence
    )
    selected = tuple(item for item in evidence if item.reason_code == CoreSelectionReason.SELECTED)
    return pairs, clusters, selected


def _coverage_evidence(
    *,
    feature_id: str,
    dates: tuple[date, ...],
    coverage_passed: bool,
) -> CoreFoldCoverageEvidence:
    reason = (
        CoreCoverageReason.PASSED if coverage_passed else CoreCoverageReason.COVERAGE_GATE_FAILED
    )
    daily = tuple(
        CoreDailyCoverageEvidence(
            decision_date=day,
            observed_count=5 if coverage_passed else 3,
            applicable_count=5,
            coverage=1.0 if coverage_passed else 0.6,
            passes_date_threshold=coverage_passed,
            reason_code=reason,
        )
        for day in dates
    )
    return CoreFoldCoverageEvidence(
        feature_id=feature_id,
        feature_definition_version="1.0.0",
        daily=daily,
        qualifying_date_count=len(dates),
        passing_date_count=len(dates) if coverage_passed else 0,
        passing_date_ratio=1.0 if coverage_passed else 0.0,
        passed=coverage_passed,
        reason_code=reason,
    )


def _turnover_transitions(
    dates: tuple[date, ...],
) -> tuple[CoreTurnoverTransitionEvidence, ...]:
    return tuple(
        CoreTurnoverTransitionEvidence(
            previous_date=previous,
            current_date=current,
            previous_n_day=5,
            current_n_day=5,
            n_common=5,
            turnover_ratio=0.0,
            valid=True,
            reason_code=CoreTurnoverReason.AVAILABLE,
        )
        for previous, current in itertools.pairwise(dates)
    )


def _feature_evidence(
    *,
    feature_id: str,
    feature_key: str,
    dates: tuple[date, ...],
    fold_id: str,
    horizon: CoreLabelHorizon,
    p_value: float | None,
    coverage_passed: bool,
    bh_result: tuple[int, float, bool] | None,
    canonical_order: int,
) -> CoreFeatureSelectionEvidence:
    coverage = _coverage_evidence(
        feature_id=feature_id,
        dates=dates,
        coverage_passed=coverage_passed,
    )
    eligible = coverage_passed and p_value is not None
    bh_rank, bh_threshold, bh_passed = bh_result or (None, None, False)
    reason = (
        CoreSelectionReason.COVERAGE_GATE_FAILED
        if not coverage_passed
        else (
            CoreSelectionReason.P_VALUE_UNAVAILABLE
            if not eligible
            else (CoreSelectionReason.SELECTED if bh_passed else CoreSelectionReason.BH_REJECTED)
        )
    )
    return CoreFeatureSelectionEvidence(
        feature_key=feature_key,
        feature_id=feature_id,
        definition_version="1.0.0",
        canonical_order=canonical_order,
        expected_direction=1,
        complexity=canonical_order,
        coverage=coverage,
        daily_rank_ic=tuple(
            CoreDailyRankICEvidence(
                decision_date=day,
                pair_count=5,
                rank_ic=1.0,
                signed_rank_ic=1.0,
            )
            for day in dates
        ),
        subfolds=tuple(
            CoreSubfoldRankICEvidence(
                subfold_id=f"subfold-{index}",
                valid_count=60,
                signed_mean_rank_ic=1.0,
                sample_sufficient=True,
            )
            for index in range(1, 4)
        ),
        direction_consistent=True,
        signed_mean_rank_ic=1.0,
        bootstrap_seed=(
            selection_seed(feature_id, "1.0.0", horizon.value, fold_id) if eligible else None
        ),
        bootstrap_p_value=p_value if eligible else None,
        selection_eligible=eligible,
        bh_rank=bh_rank,
        bh_threshold=bh_threshold,
        bh_passed=bh_passed,
        coverage_mean=1.0 if coverage_passed else 0.6,
        turnover=0.0,
        turnover_valid_transitions=len(dates) - 1,
        turnover_transitions=_turnover_transitions(dates),
        stability=1.0,
        reason_code=reason,
    )


__all__ = ["frozen_envelopes", "frozen_panel", "frozen_selection"]
