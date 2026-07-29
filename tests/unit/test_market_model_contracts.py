from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from astramind_mini.strategy_research.public import (
    DataGateState,
    DependencyVersion,
    EvidenceWindow,
    HyperparameterValue,
    MarketModelEvidenceBundle,
    MarketModelManifest,
    ModelActivation,
    ModelPredictionContext,
    ModelValidationSummary,
)

HASH = "sha256:" + "a" * 64
NOW = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


def development_window() -> EvidenceWindow:
    return EvidenceWindow(
        purpose="development",
        start=date(2013, 1, 1),
        end=date(2022, 12, 31),
    )


def manifest() -> MarketModelManifest:
    return MarketModelManifest(
        manifest_id="market-model:heat:v2:test",
        model_family="industry_heat",
        method_version="industry-heat-forecast-hgb-v2.0.0",
        baseline_method_version="industry-heat-v1.0.0",
        task="regression",
        target_definition_version="industry-excess-return-1d-v1",
        data_snapshot_id="snapshot:test",
        feature_snapshot_id="feature:test",
        training_window=development_window(),
        maturity_cutoff=date(2022, 12, 30),
        feature_names=("return_20d", "breadth", "coverage_missing"),
        estimator="sklearn.HistGradientBoostingRegressor",
        hyperparameters=(
            HyperparameterValue(name="learning_rate", value=0.05),
            HyperparameterValue(name="max_iter", value=300),
        ),
        random_seed=20260729,
        code_identity="git:test",
        dependency_versions=(DependencyVersion(package="scikit-learn", version="1.9.0"),),
        artifact_hash=HASH,
        created_at=NOW,
    )


def passing_validation() -> ModelValidationSummary:
    return ModelValidationSummary(
        validation_id="validation:test",
        manifest_id=manifest().manifest_id,
        window=EvidenceWindow(
            purpose="sealed_replay",
            start=date(2023, 1, 1),
            end=date(2025, 12, 31),
        ),
        metric_name="rank_ic",
        candidate_value=0.04,
        reference_value=0.02,
        bootstrap_lower_bound=0.01,
        subperiods_supporting=2,
        subperiods_total=3,
        coverage_not_worse=True,
        risk_not_worse=True,
        turnover_not_worse=True,
        cost_not_worse=True,
        decision="pass",
    )


def test_supported_evidence_and_readonly_activation_are_strict() -> None:
    item = manifest()
    validation = passing_validation()
    evidence = MarketModelEvidenceBundle(
        evidence_bundle_id="evidence:test",
        manifest_id=item.manifest_id,
        windows=(development_window(), validation.window),
        validations=(validation,),
        data_gates=(
            DataGateState(
                gate_name="point_in_time_membership",
                status="pass",
                observation_count=31,
                coverage_ratio=1.0,
            ),
        ),
        evidence_state="supported",
        content_hash=HASH,
        created_at=NOW,
    )
    activation = ModelActivation(
        activation_id="activation:test",
        model_family=item.model_family,
        active_method_version=item.method_version,
        active_manifest_id=item.manifest_id,
        evidence_bundle_id=evidence.evidence_bundle_id,
        state="active_v2",
        fallback_method_version=item.baseline_method_version,
        effective_at=NOW,
    )

    assert activation.broker_actions_allowed is False
    assert activation.portfolio_targets_allowed is False
    assert activation.order_plans_allowed is False


def test_supported_evidence_cannot_hide_a_failed_safety_gate() -> None:
    validation = passing_validation().model_copy(update={"risk_not_worse": False})

    with pytest.raises(ValidationError, match="safety gate"):
        ModelValidationSummary.model_validate(validation.model_dump())


def test_fallback_requires_exact_baseline_and_reason() -> None:
    with pytest.raises(ValidationError, match="fallback activation"):
        ModelActivation(
            activation_id="activation:bad",
            model_family="industry_rotation",
            active_method_version="rotation-forecast-hgb-v2.0.0",
            state="fallback_v1",
            fallback_method_version="rotation-index-ew-v1.0.0",
            reason_codes=("sealed_evidence_unsupported",),
            effective_at=NOW,
        )


def test_v2_prediction_context_requires_immutable_prediction_identities() -> None:
    with pytest.raises(ValidationError, match="manifest and batch"):
        ModelPredictionContext(
            model_family="industry_lifecycle",
            method_version="industry-lifecycle-hgb-v2.0.0",
            data_snapshot_id="snapshot:test",
            feature_snapshot_id="feature:test",
            as_of=NOW,
            horizon_sessions=20,
            evidence_state="unvalidated",
            activation_state="unvalidated_v2",
        )


def test_training_manifest_rejects_duplicate_features() -> None:
    duplicate = manifest().model_copy(update={"feature_names": ("breadth", "breadth")})

    with pytest.raises(ValidationError, match="feature_names"):
        MarketModelManifest.model_validate(duplicate.model_dump())
