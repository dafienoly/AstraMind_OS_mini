from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from astramind_mini.strategy_research.market_models.predictions import (
    ClassificationPrediction,
    ClassProbability,
    RegressionPrediction,
    freeze_prediction_batch,
)
from astramind_mini.strategy_research.market_models.recipes import recipe_for
from astramind_mini.strategy_research.market_models.splits import WalkForwardFold
from astramind_mini.strategy_research.market_models.training import (
    TabularTrainingSet,
    mean_daily_rank_ic,
    multiclass_brier,
    spearman_rank_correlation,
    train_with_grid,
)

PARAMETERS = (
    {
        "learning_rate": 0.05,
        "max_leaf_nodes": 7,
        "min_samples_leaf": 2,
        "l2_regularization": 1.0,
        "max_iter": 30,
        "max_features": 1.0,
        "random_state": 20260729,
    },
)


def fold(
    identifier: str,
    train_ids: tuple[str, ...],
    validation_ids: tuple[str, ...],
) -> WalkForwardFold:
    return WalkForwardFold(
        fold_id=identifier,
        validation_month=date(2025, 1, 1),
        train_start=datetime(2020, 1, 1, tzinfo=UTC),
        train_end=datetime(2025, 1, 1, tzinfo=UTC),
        maturity_cutoff=datetime(2026, 1, 1, tzinfo=UTC),
        train_sample_ids=train_ids,
        validation_sample_ids=validation_ids,
    )


def test_average_tie_rank_and_brier_are_reproducible() -> None:
    assert spearman_rank_correlation(
        np.asarray([1.0, 1.0, 2.0, 3.0]),
        np.asarray([10.0, 10.0, 20.0, 30.0]),
    ) == pytest.approx(1.0)
    assert multiclass_brier(
        np.asarray(["a", "b"]),
        np.asarray([[0.8, 0.2], [0.1, 0.9]]),
        np.asarray(["a", "b"]),
    ) == pytest.approx(0.05)


def test_rank_ic_is_meaned_by_daily_cross_section_and_skips_invalid_days() -> None:
    feature_at = (
        *(datetime(2025, 1, 2, tzinfo=UTC) for _ in range(3)),
        *(datetime(2025, 1, 3, tzinfo=UTC) for _ in range(3)),
        *(datetime(2025, 1, 6, tzinfo=UTC) for _ in range(3)),
    )
    actual = np.asarray([1.0, 2.0, 3.0, 100.0, 200.0, 300.0, 7.0, 7.0, 7.0])
    predicted = np.asarray([1.0, 2.0, 3.0, 300.0, 200.0, 100.0, 1.0, 2.0, 3.0])

    daily = mean_daily_rank_ic(actual, predicted, feature_at)
    pooled = spearman_rank_correlation(actual, predicted)

    assert daily == pytest.approx(0.0)
    assert pooled != pytest.approx(daily)


def test_regression_training_uses_explicit_time_folds_and_native_missing() -> None:
    sample_ids = tuple(f"sample:{index:03d}" for index in range(90))
    base = np.linspace(-2.0, 2.0, 90)
    features = np.column_stack((base, base**2))
    features[5, 1] = np.nan
    dataset = TabularTrainingSet(
        sample_ids=sample_ids,
        feature_at=_feature_times(len(sample_ids)),
        feature_names=("trend", "volatility"),
        features=features,
        labels=base * 2.0 + 0.1,
    )
    folds = (
        fold("fold:1", sample_ids[:50], sample_ids[50:70]),
        fold("fold:2", sample_ids[:70], sample_ids[70:]),
    )

    first = train_with_grid(
        dataset,
        recipe=recipe_for("industry_heat"),
        folds=folds,
        parameter_grid=PARAMETERS,
    )
    second = train_with_grid(
        dataset,
        recipe=recipe_for("industry_heat"),
        folds=folds,
        parameter_grid=PARAMETERS,
    )

    assert first.validation_score == pytest.approx(second.validation_score)
    assert all(item.rank_ic is not None for item in first.fold_metrics)
    assert first.estimator.early_stopping is False
    assert np.allclose(
        first.estimator.predict(features),
        second.estimator.predict(features),
    )


def test_lifecycle_training_reports_macro_f1_and_brier() -> None:
    sample_ids = tuple(f"sample:{index:03d}" for index in range(120))
    labels = np.asarray([index % 6 for index in range(120)])
    features = np.column_stack((labels.astype(float), np.arange(120) % 5))
    dataset = TabularTrainingSet(
        sample_ids=sample_ids,
        feature_at=_feature_times(len(sample_ids)),
        feature_names=("future_structure_proxy", "coverage"),
        features=features,
        labels=labels,
    )
    result = train_with_grid(
        dataset,
        recipe=recipe_for("industry_lifecycle"),
        folds=(
            fold("fold:1", sample_ids[:72], sample_ids[72:96]),
            fold("fold:2", sample_ids[:96], sample_ids[96:]),
        ),
        parameter_grid=PARAMETERS,
    )

    assert all(item.macro_f1 is not None for item in result.fold_metrics)
    assert all(item.brier is not None for item in result.fold_metrics)
    assert result.estimator.early_stopping is False


def test_training_rejects_infinite_features_and_empty_folds() -> None:
    with pytest.raises(ValueError, match="not infinity"):
        TabularTrainingSet(
            sample_ids=("sample:1",),
            feature_at=_feature_times(1),
            feature_names=("feature",),
            features=np.asarray([[np.inf]]),
            labels=np.asarray([1.0]),
        )

    dataset = TabularTrainingSet(
        sample_ids=("sample:1", "sample:2"),
        feature_at=_feature_times(2),
        feature_names=("feature",),
        features=np.asarray([[1.0], [2.0]]),
        labels=np.asarray([1.0, 2.0]),
    )
    with pytest.raises(ValueError, match="explicit time fold"):
        train_with_grid(
            dataset,
            recipe=recipe_for("industry_heat"),
            folds=(),
            parameter_grid=PARAMETERS,
        )


def _feature_times(count: int) -> tuple[datetime, ...]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return tuple(start + timedelta(days=index // 3) for index in range(count))


def test_prediction_batches_are_content_addressed_and_readonly() -> None:
    as_of = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)
    regression = freeze_prediction_batch(
        model_family="industry_rotation",
        manifest_id="manifest:rotation",
        data_snapshot_id="snapshot:test",
        feature_snapshot_id="feature:test",
        as_of=as_of,
        horizons=(5, 20),
        evidence_state="unvalidated",
        regressions=(
            RegressionPrediction(
                entity_id="801080.SI",
                horizon_sessions=5,
                predicted_value=0.02,
                standardized_value=0.8,
            ),
            RegressionPrediction(
                entity_id="801080.SI",
                horizon_sessions=20,
                predicted_value=0.05,
                standardized_value=0.6,
            ),
        ),
    )
    classification = freeze_prediction_batch(
        model_family="industry_lifecycle",
        manifest_id="manifest:lifecycle",
        data_snapshot_id="snapshot:test",
        feature_snapshot_id="feature:test",
        as_of=as_of,
        horizons=(20,),
        evidence_state="unvalidated",
        classifications=(
            ClassificationPrediction(
                entity_id="801080.SI",
                horizon_sessions=20,
                predicted_label="strong_expansion",
                probabilities=(
                    ClassProbability(label="strong_expansion", probability=0.7),
                    ClassProbability(label="unclear", probability=0.3),
                ),
            ),
        ),
    )

    assert regression.prediction_batch_id.startswith("market-prediction:")
    assert regression.broker_actions_allowed is False
    assert classification.broker_actions_allowed is False
