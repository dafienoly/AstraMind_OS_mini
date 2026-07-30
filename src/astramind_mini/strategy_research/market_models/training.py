"""Explicit-time-fold HistGradientBoosting training for market models."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
from sklearn.ensemble import (  # type: ignore[import-untyped]
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.metrics import f1_score  # type: ignore[import-untyped]

from .recipes import COMMON_GRID, MarketModelRecipe
from .splits import WalkForwardFold


@dataclass(frozen=True)
class TabularTrainingSet:
    sample_ids: tuple[str, ...]
    feature_at: tuple[datetime, ...]
    feature_names: tuple[str, ...]
    features: np.ndarray
    labels: np.ndarray

    def __post_init__(self) -> None:
        if self.features.ndim != 2 or self.labels.ndim != 1:
            raise ValueError("features must be 2D and labels must be 1D")
        if self.features.shape != (len(self.sample_ids), len(self.feature_names)):
            raise ValueError("training feature shape does not match identities")
        if self.labels.shape[0] != len(self.sample_ids):
            raise ValueError("training labels do not match sample identities")
        if len(self.feature_at) != len(self.sample_ids):
            raise ValueError("training feature times do not match sample identities")
        if any(value.tzinfo is None or value.utcoffset() is None for value in self.feature_at):
            raise ValueError("training feature times must be timezone-aware")
        if len(set(self.sample_ids)) != len(self.sample_ids):
            raise ValueError("training sample identities must be unique")
        if np.isinf(self.features).any():
            raise ValueError("features may contain NaN but not infinity")
        if not np.isfinite(self.labels).all():
            raise ValueError("training labels must be finite")


@dataclass(frozen=True)
class FoldMetric:
    fold_id: str
    primary_score: float
    rank_ic: float | None = None
    macro_f1: float | None = None
    brier: float | None = None


@dataclass(frozen=True)
class TrainedMarketModel:
    estimator: Any
    parameters: Mapping[str, bool | int | float | str]
    validation_score: float
    fold_metrics: tuple[FoldMetric, ...]


def train_with_grid(
    dataset: TabularTrainingSet,
    *,
    recipe: MarketModelRecipe,
    folds: Sequence[WalkForwardFold],
    parameter_grid: Sequence[Mapping[str, bool | int | float | str]] = COMMON_GRID,
) -> TrainedMarketModel:
    if not folds:
        raise ValueError("at least one explicit time fold is required")
    index = {sample_id: position for position, sample_id in enumerate(dataset.sample_ids)}
    candidates: list[
        tuple[float, str, Mapping[str, bool | int | float | str], tuple[FoldMetric, ...]]
    ] = []
    for parameters in parameter_grid:
        metrics = _evaluate_parameters(
            dataset,
            recipe=recipe,
            folds=folds,
            index=index,
            parameters=parameters,
        )
        if metrics:
            score = float(np.mean([item.primary_score for item in metrics]))
            candidates.append((score, _parameter_identity(parameters), parameters, metrics))
    if not candidates:
        raise ValueError("no time fold contained usable train and validation samples")
    score, _, selected, metrics = max(candidates, key=lambda item: (item[0], item[1]))
    estimator = _build_estimator(recipe, selected)
    estimator.fit(dataset.features, dataset.labels)
    return TrainedMarketModel(
        estimator=estimator,
        parameters=dict(selected),
        validation_score=score,
        fold_metrics=metrics,
    )


def _evaluate_parameters(
    dataset: TabularTrainingSet,
    *,
    recipe: MarketModelRecipe,
    folds: Sequence[WalkForwardFold],
    index: Mapping[str, int],
    parameters: Mapping[str, bool | int | float | str],
) -> tuple[FoldMetric, ...]:
    metrics: list[FoldMetric] = []
    for fold in folds:
        train_indexes = [index[item] for item in fold.train_sample_ids if item in index]
        validation_indexes = [index[item] for item in fold.validation_sample_ids if item in index]
        if not train_indexes or not validation_indexes:
            continue
        estimator = _build_estimator(recipe, parameters)
        estimator.fit(dataset.features[train_indexes], dataset.labels[train_indexes])
        metrics.append(
            _score_fold(
                recipe,
                fold.fold_id,
                dataset.labels[validation_indexes],
                estimator,
                dataset.features[validation_indexes],
                tuple(dataset.feature_at[index] for index in validation_indexes),
            )
        )
    return tuple(item for item in metrics if math.isfinite(item.primary_score))


def _build_estimator(
    recipe: MarketModelRecipe,
    parameters: Mapping[str, bool | int | float | str],
) -> HistGradientBoostingRegressor | HistGradientBoostingClassifier:
    settings = {**parameters, "early_stopping": False}
    if recipe.task == "classification":
        return HistGradientBoostingClassifier(**settings)
    return HistGradientBoostingRegressor(**settings)


def _score_fold(
    recipe: MarketModelRecipe,
    fold_id: str,
    actual: np.ndarray,
    estimator: HistGradientBoostingRegressor | HistGradientBoostingClassifier,
    features: np.ndarray,
    feature_at: Sequence[datetime],
) -> FoldMetric:
    predicted = estimator.predict(features)
    if recipe.task == "regression":
        rank_ic = mean_daily_rank_ic(
            actual.astype(float),
            predicted.astype(float),
            feature_at,
        )
        return FoldMetric(fold_id=fold_id, primary_score=rank_ic, rank_ic=rank_ic)
    macro_f1 = float(f1_score(actual, predicted, average="macro", zero_division=0))
    probabilities = estimator.predict_proba(features)
    classes = estimator.classes_
    brier = multiclass_brier(actual, probabilities, classes)
    return FoldMetric(
        fold_id=fold_id,
        primary_score=macro_f1 - brier,
        macro_f1=macro_f1,
        brier=brier,
    )


def mean_daily_rank_ic(
    actual: np.ndarray,
    predicted: np.ndarray,
    feature_at: Sequence[datetime],
) -> float:
    if len(actual) != len(predicted) or len(actual) != len(feature_at):
        raise ValueError("daily RankIC inputs must have matching lengths")
    by_day: dict[date, list[int]] = {}
    for index, timestamp in enumerate(feature_at):
        by_day.setdefault(timestamp.date(), []).append(index)
    daily_scores = tuple(
        score
        for indexes in by_day.values()
        for score in (
            spearman_rank_correlation(
                actual[np.asarray(indexes, dtype=int)],
                predicted[np.asarray(indexes, dtype=int)],
            ),
        )
        if math.isfinite(score)
    )
    if not daily_scores:
        return float("nan")
    return float(np.mean(daily_scores))


def spearman_rank_correlation(actual: np.ndarray, predicted: np.ndarray) -> float:
    if len(actual) < 2 or len(predicted) != len(actual):
        return float("nan")
    actual_rank = _average_ranks(actual)
    predicted_rank = _average_ranks(predicted)
    if np.std(actual_rank) == 0 or np.std(predicted_rank) == 0:
        return float("nan")
    return float(np.corrcoef(actual_rank, predicted_rank)[0, 1])


def multiclass_brier(
    actual: np.ndarray,
    probabilities: np.ndarray,
    classes: np.ndarray,
) -> float:
    if probabilities.shape != (len(actual), len(classes)):
        raise ValueError("probability matrix does not match classes")
    class_index = {value: index for index, value in enumerate(classes.tolist())}
    observed = np.zeros_like(probabilities, dtype=float)
    for row, value in enumerate(actual.tolist()):
        if value not in class_index:
            raise ValueError("actual class absent from fitted estimator")
        observed[row, class_index[value]] = 1.0
    return float(np.mean(np.sum((probabilities - observed) ** 2, axis=1)))


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def _parameter_identity(parameters: Mapping[str, bool | int | float | str]) -> str:
    return "|".join(f"{key}={parameters[key]}" for key in sorted(parameters))


__all__ = [
    "FoldMetric",
    "TabularTrainingSet",
    "TrainedMarketModel",
    "mean_daily_rank_ic",
    "multiclass_brier",
    "spearman_rank_correlation",
    "train_with_grid",
]
