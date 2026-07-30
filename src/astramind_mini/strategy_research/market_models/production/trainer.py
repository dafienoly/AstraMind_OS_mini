"""Reproducible multi-horizon training and inference over one frozen matrix."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor  # type: ignore[import-untyped]

from ..predictions import RegressionPrediction
from ..recipes import MarketModelRecipe
from ..splits import build_walk_forward_folds, final_training_sample_ids
from ..training import TabularTrainingSet, train_with_grid
from .contracts import ProductionFeatureMatrix
from .matrix import inference_set, point_in_time_samples, training_set
from .snapshot import ProductionInputError


@dataclass(frozen=True)
class ProductionTrainedBundle:
    estimators: dict[str, Any]
    parameters: dict[int, Mapping[str, bool | int | float | str]]
    training_start: date
    training_end: date
    maturity_cutoff: date
    mature_sample_count: int
    label_candidate_sample_count: int


class ProductionModelTrainer:
    def train(
        self,
        matrix: ProductionFeatureMatrix,
        *,
        recipe: MarketModelRecipe,
        maturity_cutoff: datetime,
        parameter_grid: Sequence[Mapping[str, bool | int | float | str]],
    ) -> ProductionTrainedBundle:
        estimators: dict[str, Any] = {}
        parameters: dict[int, Mapping[str, bool | int | float | str]] = {}
        selected_dates: list[date] = []
        mature_count = 0
        candidate_count = 0
        for horizon in recipe.horizons:
            samples = point_in_time_samples(matrix, horizon=horizon)
            folds = tuple(
                fold
                for fold in build_walk_forward_folds(
                    samples,
                    recipe=recipe,
                    purpose="development",
                    evidence_cutoff=maturity_cutoff,
                )
                if fold.train_sample_ids and fold.validation_sample_ids
            )
            final_ids = final_training_sample_ids(
                samples,
                recipe=recipe,
                purpose="development",
                training_at=maturity_cutoff,
            )
            if not folds:
                raise ProductionInputError(f"walk_forward_folds_unusable:h{horizon}")
            if len(final_ids) < 3:
                raise ProductionInputError(f"label_mature_samples_insufficient:h{horizon}")
            evaluation_ids = tuple(
                sorted(
                    {
                        *final_ids,
                        *(
                            sample_id
                            for fold in folds
                            for sample_id in (
                                *fold.train_sample_ids,
                                *fold.validation_sample_ids,
                            )
                        ),
                    }
                )
            )
            evaluation = training_set(
                matrix,
                horizon=horizon,
                sample_ids=evaluation_ids,
            )
            selected = train_with_grid(
                evaluation,
                recipe=recipe,
                folds=folds,
                parameter_grid=parameter_grid,
            )
            final = training_set(matrix, horizon=horizon, sample_ids=final_ids)
            estimators[str(horizon)] = _fit_final(final, selected.parameters)
            parameters[horizon] = selected.parameters
            samples_by_id = {sample.sample_id: sample for sample in samples}
            training_start = _years_before(maturity_cutoff, recipe.rolling_years)
            candidate_count += sum(
                training_start <= sample.feature_at <= maturity_cutoff for sample in samples
            )
            selected_dates.extend(
                samples_by_id[sample_id].feature_at.date() for sample_id in final_ids
            )
            mature_count += len(final_ids)
        if not selected_dates:
            raise ProductionInputError("label_mature_samples_empty")
        return ProductionTrainedBundle(
            estimators=estimators,
            parameters=parameters,
            training_start=min(selected_dates),
            training_end=maturity_cutoff.date(),
            maturity_cutoff=maturity_cutoff.date(),
            mature_sample_count=mature_count,
            label_candidate_sample_count=candidate_count,
        )

    def predict(
        self,
        matrix: ProductionFeatureMatrix,
        *,
        recipe: MarketModelRecipe,
        trained: ProductionTrainedBundle,
    ) -> tuple[RegressionPrediction, ...]:
        result: list[RegressionPrediction] = []
        for horizon in recipe.horizons:
            entities, features = inference_set(matrix, horizon=horizon)
            estimator = trained.estimators[str(horizon)]
            predicted = np.asarray(estimator.predict(features), dtype=float)
            if predicted.shape != (len(entities),) or not np.isfinite(predicted).all():
                raise ValueError("production inference returned invalid values")
            standardized = _standardize(predicted)
            result.extend(
                RegressionPrediction(
                    entity_id=entity,
                    horizon_sessions=horizon,
                    predicted_value=float(value),
                    standardized_value=float(score),
                )
                for entity, value, score in zip(
                    entities,
                    predicted,
                    standardized,
                    strict=True,
                )
            )
        return tuple(result)


def canonical_parameter_grid(
    parameter_grid: Sequence[Mapping[str, bool | int | float | str]],
) -> tuple[tuple[tuple[str, bool | int | float | str], ...], ...]:
    return tuple(
        tuple((key, parameters[key]) for key in sorted(parameters)) for parameters in parameter_grid
    )


def _fit_final(
    dataset: TabularTrainingSet,
    parameters: Mapping[str, bool | int | float | str],
) -> HistGradientBoostingRegressor:
    estimator = HistGradientBoostingRegressor(
        **parameters,
        early_stopping=False,
    )
    estimator.fit(dataset.features, dataset.labels)
    return estimator


def _standardize(values: np.ndarray) -> np.ndarray:
    deviation = float(np.std(values))
    if deviation < 1e-12:
        return np.zeros_like(values)
    return (values - float(np.mean(values))) / deviation


def _years_before(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


__all__ = [
    "ProductionModelTrainer",
    "ProductionTrainedBundle",
    "canonical_parameter_grid",
]
