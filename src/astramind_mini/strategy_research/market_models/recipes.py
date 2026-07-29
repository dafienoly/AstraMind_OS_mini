"""Frozen recipes shared by the five read-only market model families."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from types import MappingProxyType
from typing import Literal

from .contracts import MarketModelFamily

EstimatorTask = Literal["regression", "classification"]


@dataclass(frozen=True)
class MarketModelRecipe:
    family: MarketModelFamily
    method_version: str
    baseline_method_version: str
    target_definition_version: str
    task: EstimatorTask
    horizons: tuple[int, ...]
    rolling_years: int
    validation_months: int = 12
    random_seed: int = 20260729


COMMON_GRID = tuple(
    {
        "learning_rate": learning_rate,
        "max_leaf_nodes": max_leaf_nodes,
        "min_samples_leaf": min_samples_leaf,
        "l2_regularization": l2_regularization,
        "max_iter": 300,
        "max_features": 1.0,
        "random_state": 20260729,
    }
    for learning_rate, max_leaf_nodes, min_samples_leaf, l2_regularization in product(
        (0.03, 0.05),
        (7, 15),
        (50, 100),
        (1.0, 5.0),
    )
)

RECIPES = MappingProxyType(
    {
        "industry_heat": MarketModelRecipe(
            family="industry_heat",
            method_version="industry-heat-forecast-hgb-v2.0.0",
            baseline_method_version="industry-heat-v1.0.0",
            target_definition_version="industry-excess-return-1d-5d-v1",
            task="regression",
            horizons=(1, 5),
            rolling_years=10,
        ),
        "industry_rotation": MarketModelRecipe(
            family="industry_rotation",
            method_version="rotation-forecast-hgb-v2.0.0",
            baseline_method_version="rotation-index-ew-v1.0.0",
            target_definition_version="industry-excess-return-5d-20d-v1",
            task="regression",
            horizons=(5, 20),
            rolling_years=10,
        ),
        "industry_lifecycle": MarketModelRecipe(
            family="industry_lifecycle",
            method_version="industry-lifecycle-hgb-v2.0.0",
            baseline_method_version="lifecycle-structure-v1.0.0",
            target_definition_version="industry-lifecycle-six-stage-v1",
            task="classification",
            horizons=(20,),
            rolling_years=5,
        ),
        "industry_research_ranking": MarketModelRecipe(
            family="industry_research_ranking",
            method_version="industry-research-ranking-hgb-v2.0.0",
            baseline_method_version="industry-research-priority-v1.0.0",
            target_definition_version="industry-relative-rank-20d-60d-v1",
            task="regression",
            horizons=(20, 60),
            rolling_years=5,
        ),
        "etf_rotation": MarketModelRecipe(
            family="etf_rotation",
            method_version="etf-rotation-hgb-v2.0.0",
            baseline_method_version="etf-rotation-research-v1.0.0",
            target_definition_version="etf-net-official-benchmark-excess-20d-v1",
            task="regression",
            horizons=(20,),
            rolling_years=3,
        ),
    }
)


def recipe_for(family: MarketModelFamily) -> MarketModelRecipe:
    return RECIPES[family]


def market_model_catalog() -> tuple[MarketModelRecipe, ...]:
    return tuple(RECIPES.values())


__all__ = [
    "COMMON_GRID",
    "RECIPES",
    "MarketModelRecipe",
    "market_model_catalog",
    "recipe_for",
]
