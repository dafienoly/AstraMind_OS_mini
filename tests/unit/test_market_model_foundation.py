from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor  # type: ignore[import-untyped]

from astramind_mini.strategy_research.market_models.activation_store import (
    ModelActivationStore,
)
from astramind_mini.strategy_research.market_models.artifacts import (
    SerializedModel,
    SkopsArtifactStore,
)
from astramind_mini.strategy_research.market_models.contracts import (
    DependencyVersion,
    HyperparameterValue,
)
from astramind_mini.strategy_research.market_models.identity import (
    freeze_activation,
    freeze_manifest,
)
from astramind_mini.strategy_research.market_models.recipes import (
    COMMON_GRID,
    RECIPES,
    recipe_for,
)
from astramind_mini.strategy_research.market_models.samples import (
    PointInTimeSample,
    eligibility_reason,
    sample_is_eligible,
)
from astramind_mini.strategy_research.market_models.splits import (
    build_walk_forward_folds,
    final_training_sample_ids,
)

NOW = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)


def sample(
    identifier: str,
    feature_at: datetime,
    *,
    label_delay_days: int = 30,
    membership: str = "known_at_decision",
) -> PointInTimeSample:
    label_end = feature_at + timedelta(days=20)
    return PointInTimeSample.model_validate(
        {
            "sample_id": identifier,
            "entity_id": "801080.SI",
            "feature_at": feature_at,
            "label_end_at": label_end,
            "label_available_at": label_end + timedelta(days=label_delay_days),
            "membership_knowledge": membership,
        }
    )


def test_five_recipes_and_fixed_grid_match_the_approved_plan() -> None:
    assert set(RECIPES) == {
        "industry_heat",
        "industry_rotation",
        "industry_lifecycle",
        "industry_research_ranking",
        "etf_rotation",
    }
    assert len(COMMON_GRID) == 16
    assert recipe_for("industry_heat").rolling_years == 10
    assert recipe_for("industry_rotation").horizons == (5, 20)
    assert recipe_for("industry_lifecycle").task == "classification"
    assert recipe_for("industry_research_ranking").rolling_years == 5
    assert recipe_for("etf_rotation").rolling_years == 3
    assert all(item["random_state"] == 20260729 for item in COMMON_GRID)


def test_reconstructed_membership_is_rejected_outside_development() -> None:
    reconstructed = sample(
        "sample:reconstructed",
        datetime(2020, 6, 1, tzinfo=UTC),
        membership="reconstructed_not_then_known",
    )
    cutoff = datetime(2021, 1, 1, tzinfo=UTC)

    assert sample_is_eligible(
        reconstructed,
        purpose="development",
        evidence_cutoff=cutoff,
    )
    assert not sample_is_eligible(
        reconstructed,
        purpose="sealed_replay",
        evidence_cutoff=cutoff,
    )
    assert (
        eligibility_reason(
            reconstructed,
            purpose="sealed_replay",
            evidence_cutoff=cutoff,
        )
        == "membership_reconstructed_not_then_known"
    )


def test_walk_forward_purges_unmature_labels_and_is_deterministic() -> None:
    samples = (
        sample("sample:train", datetime(2023, 1, 5, tzinfo=UTC), label_delay_days=0),
        sample("sample:late", datetime(2023, 11, 1, tzinfo=UTC), label_delay_days=90),
        sample("sample:validate", datetime(2024, 1, 5, tzinfo=UTC), label_delay_days=0),
    )
    recipe = recipe_for("industry_lifecycle")
    cutoff = datetime(2024, 4, 1, tzinfo=UTC)

    first = build_walk_forward_folds(
        samples,
        recipe=recipe,
        purpose="sealed_replay",
        evidence_cutoff=cutoff,
    )
    second = build_walk_forward_folds(
        samples,
        recipe=recipe,
        purpose="sealed_replay",
        evidence_cutoff=cutoff,
    )
    january = next(item for item in first if item.validation_month == date(2024, 1, 1))

    assert first == second
    assert january.train_sample_ids == ("sample:train",)
    assert january.validation_sample_ids == ("sample:validate",)
    assert "sample:late" not in january.train_sample_ids


def test_final_training_only_includes_labels_mature_at_training_time() -> None:
    samples = (
        sample("sample:mature", datetime(2025, 1, 1, tzinfo=UTC), label_delay_days=0),
        sample("sample:not-mature", datetime(2026, 7, 1, tzinfo=UTC), label_delay_days=90),
    )

    selected = final_training_sample_ids(
        samples,
        recipe=recipe_for("industry_heat"),
        purpose="prospective",
        training_at=NOW,
    )

    assert selected == ("sample:mature",)


def test_skops_artifact_round_trip_and_tamper_detection(tmp_path: Path) -> None:
    model = HistGradientBoostingRegressor(max_iter=3, random_state=20260729)
    features = np.asarray([[0.0], [1.0], [2.0], [3.0]])
    model.fit(features, np.asarray([0.0, 1.0, 2.0, 3.0]))
    store = SkopsArtifactStore(tmp_path)
    serialized = store.serialize(model)
    path = store.publish(serialized)

    restored = store.load(serialized.content_hash)
    assert np.allclose(restored.predict(features), model.predict(features))

    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="内容哈希"):
        store.load(serialized.content_hash)


def test_artifact_publish_rejects_false_content_identity(tmp_path: Path) -> None:
    store = SkopsArtifactStore(tmp_path)
    with pytest.raises(ValueError, match="身份与内容"):
        store.publish(
            SerializedModel(
                payload=b"not-a-model",
                content_hash="sha256:" + "0" * 64,
            )
        )


def test_manifest_and_activation_identities_are_stable(tmp_path: Path) -> None:
    recipe = recipe_for("industry_heat")
    first_manifest = freeze_manifest(
        recipe=recipe,
        data_snapshot_id="snapshot:test",
        feature_snapshot_id="feature:test",
        training_start=date(2013, 1, 1),
        training_end=date(2022, 12, 31),
        maturity_cutoff=date(2022, 12, 30),
        feature_names=("return_20d", "breadth"),
        estimator="sklearn.HistGradientBoostingRegressor",
        hyperparameters=(HyperparameterValue(name="max_iter", value=300),),
        code_identity="git:test",
        dependency_versions=(DependencyVersion(package="scikit-learn", version="1.9.0"),),
        artifact_hash="sha256:" + "a" * 64,
        created_at=NOW,
    )
    second_manifest = freeze_manifest(
        recipe=recipe,
        data_snapshot_id="snapshot:test",
        feature_snapshot_id="feature:test",
        training_start=date(2013, 1, 1),
        training_end=date(2022, 12, 31),
        maturity_cutoff=date(2022, 12, 30),
        feature_names=("return_20d", "breadth"),
        estimator="sklearn.HistGradientBoostingRegressor",
        hyperparameters=(HyperparameterValue(name="max_iter", value=300),),
        code_identity="git:test",
        dependency_versions=(DependencyVersion(package="scikit-learn", version="1.9.0"),),
        artifact_hash="sha256:" + "a" * 64,
        created_at=NOW,
    )
    assert first_manifest == second_manifest

    activation = freeze_activation(
        model_family="industry_heat",
        active_method_version=recipe.method_version,
        active_manifest_id=first_manifest.manifest_id,
        evidence_bundle_id="evidence:test",
        state="unvalidated_v2",
        fallback_method_version=recipe.baseline_method_version,
        effective_at=NOW,
    )
    store = ModelActivationStore(tmp_path / "activations")
    store.publish(activation)

    assert store.current("industry_heat") == activation
