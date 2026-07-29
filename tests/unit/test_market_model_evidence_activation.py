from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from astramind_mini.strategy_research.market_models.activation_policy import (
    activation_for_evidence,
)
from astramind_mini.strategy_research.market_models.contracts import (
    DataGateState,
    DependencyVersion,
    EvidenceWindow,
    MarketModelEvidenceBundle,
    MarketModelManifest,
    ModelValidationSummary,
)
from astramind_mini.strategy_research.market_models.evidence import (
    freeze_evidence_bundle,
)
from astramind_mini.strategy_research.market_models.evidence_store import (
    MarketModelEvidenceStore,
)
from astramind_mini.strategy_research.market_models.identity import freeze_manifest
from astramind_mini.strategy_research.market_models.monthly_activation import (
    MarketModelCandidate,
    MonthlyMarketModelActivationService,
)
from astramind_mini.strategy_research.market_models.recipes import recipe_for
from astramind_mini.strategy_research.market_models.validation import (
    LifecycleEvidence,
    SafetyGates,
    block_bootstrap_mean,
    validate_lifecycle,
    validate_rank_series,
)

NOW = datetime(2026, 7, 29, 10, tzinfo=UTC)
SEALED = EvidenceWindow(
    purpose="sealed_replay",
    start=date(2023, 1, 1),
    end=date(2025, 12, 31),
)
SAFE = SafetyGates(
    coverage_not_worse=True,
    risk_not_worse=True,
    turnover_not_worse=True,
    cost_not_worse=True,
)


def test_block_bootstrap_and_rank_support_are_deterministic() -> None:
    values = tuple(0.05 + index / 10_000 for index in range(120))
    first = block_bootstrap_mean(values, block_size=20)
    second = block_bootstrap_mean(values, block_size=20)
    assert first == second
    assert first.lower_bound > 0

    passed = validate_rank_series(
        manifest_id="manifest:test",
        window=SEALED,
        candidate_values=values,
        reference_values=tuple(0.01 for _ in values),
        safety=SAFE,
    )
    assert passed.decision == "pass"
    assert passed.subperiods_supporting == 3

    failed = validate_rank_series(
        manifest_id="manifest:test",
        window=SEALED,
        candidate_values=tuple(-value for value in values),
        reference_values=tuple(0.0 for _ in values),
        safety=SAFE,
    )
    assert failed.decision == "fail"
    assert "bootstrap_lower_bound_not_positive" in failed.reason_codes


def test_lifecycle_requires_all_four_metrics_and_safety() -> None:
    summaries = validate_lifecycle(
        manifest_id="manifest:lifecycle",
        window=SEALED,
        evidence=LifecycleEvidence(
            macro_f1=0.51,
            reference_macro_f1=0.50,
            brier=0.31,
            reference_brier=0.30,
            calibration_error=0.09,
            reference_calibration_error=0.10,
            stage_return_monotonicity=0.8,
            reference_stage_return_monotonicity=0.7,
        ),
        safety=SAFE,
    )
    assert len(summaries) == 4
    assert next(item for item in summaries if item.metric_name == "brier").decision == "fail"
    assert any(item.decision == "pass" for item in summaries)


def test_etf_supported_evidence_without_four_data_gates_falls_back() -> None:
    manifest = _manifest("etf_rotation")
    validation = _passing_validation(manifest)
    evidence = freeze_evidence_bundle(
        manifest_id=manifest.manifest_id,
        windows=(SEALED,),
        validations=(validation,),
        data_gates=(),
        evidence_state="supported",
        created_at=NOW,
    )
    activation = activation_for_evidence(
        manifest=manifest,
        evidence=evidence,
        effective_at=NOW,
    )
    assert activation.state == "fallback_v1"
    assert "etf_data_gate_missing:l1_spread_60d" in activation.reason_codes


def test_evidence_store_verifies_content_identity(tmp_path: Path) -> None:
    manifest = _manifest("industry_heat")
    evidence = _supported_evidence(manifest)
    store = MarketModelEvidenceStore(tmp_path)
    store.publish(evidence)
    assert store.load(evidence.evidence_bundle_id) == evidence

    tampered = evidence.model_copy(update={"evidence_state": "unsupported"})
    with pytest.raises(ValueError, match="身份与内容不一致"):
        store.publish(tampered)


def test_monthly_activation_publishes_only_integrity_checked_supported_candidate(
    tmp_path: Path,
) -> None:
    manifest = _manifest("industry_heat")
    evidence = _supported_evidence(manifest)
    validated: list[str] = []
    service = MonthlyMarketModelActivationService(
        root=tmp_path,
        artifact_validator=lambda digest: validated.append(digest),
    )
    result = service.reconcile(
        (MarketModelCandidate(manifest, evidence),),
        effective_at=NOW,
    )[0]
    assert result.state == "active_v2"
    assert validated == [manifest.artifact_hash]

    repeated = service.reconcile(
        (MarketModelCandidate(manifest, evidence),),
        effective_at=NOW,
    )[0]
    assert "monthly_activation_already_recorded" in repeated.reason_codes


def test_monthly_activation_fails_closed_when_artifact_is_invalid(tmp_path: Path) -> None:
    manifest = _manifest("industry_rotation")
    evidence = _supported_evidence(manifest)

    def reject(_: str) -> object:
        raise ValueError("corrupt")

    result = MonthlyMarketModelActivationService(
        root=tmp_path,
        artifact_validator=reject,
    ).reconcile(
        (MarketModelCandidate(manifest, evidence),),
        effective_at=NOW,
    )[0]
    assert result.state == "fallback_v1"
    assert result.reason_codes == ("candidate_integrity_failed",)


def _manifest(family: str) -> MarketModelManifest:
    return freeze_manifest(
        recipe=recipe_for(family),  # type: ignore[arg-type]
        data_snapshot_id="snapshot:test",
        feature_snapshot_id="features:test",
        training_start=date(2013, 1, 1),
        training_end=date(2022, 12, 31),
        maturity_cutoff=date(2022, 12, 31),
        feature_names=("return_20d", "coverage"),
        estimator="HistGradientBoostingRegressor",
        hyperparameters=(),
        code_identity="test",
        dependency_versions=(DependencyVersion(package="scikit-learn", version="1.9.0"),),
        artifact_hash="sha256:" + "a" * 64,
        created_at=NOW,
    )


def _passing_validation(manifest: MarketModelManifest) -> ModelValidationSummary:
    return validate_rank_series(
        manifest_id=manifest.manifest_id,
        window=SEALED,
        candidate_values=tuple(0.1 for _ in range(120)),
        reference_values=tuple(0.05 for _ in range(120)),
        safety=SAFE,
    )


def _supported_evidence(
    manifest: MarketModelManifest,
) -> MarketModelEvidenceBundle:
    return freeze_evidence_bundle(
        manifest_id=manifest.manifest_id,
        windows=(SEALED,),
        validations=(_passing_validation(manifest),),
        data_gates=(
            (
                DataGateState(
                    gate_name="coverage",
                    status="pass",
                    observation_count=120,
                    coverage_ratio=1.0,
                )
            ),
        ),
        evidence_state="supported",
        created_at=NOW,
    )
