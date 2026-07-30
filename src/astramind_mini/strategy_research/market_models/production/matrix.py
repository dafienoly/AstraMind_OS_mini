"""Build and consume content-addressed historical feature matrices."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import numpy as np

from ...application.identity import research_hash
from ..recipes import recipe_for
from ..samples import PointInTimeSample
from ..training import TabularTrainingSet
from .contracts import (
    ProductionFamily,
    ProductionFeatureMatrix,
    ProductionFeatureRow,
    ProductionInferenceRow,
)
from .feature_math import FeaturePanel
from .identity import freeze_feature_matrix
from .snapshot import ProductionInputError
from .source import ProductionHistory

SHANGHAI = ZoneInfo("Asia/Shanghai")
DEVELOPMENT_END = date(2022, 12, 31)
DEVELOPMENT_START_REQUIRED = date(2012, 12, 31)
DEFINITION_VERSIONS = {
    "industry_heat": "industry-heat-production-features-v1.0.0",
    "industry_rotation": "industry-rotation-production-features-v1.0.0",
}
FEATURE_WARMUP_SESSIONS = {
    "industry_heat": 60,
    "industry_rotation": 140,
}


class ProductionFeatureMatrixBuilder:
    def build(
        self,
        *,
        family: ProductionFamily,
        data_snapshot_id: str,
        history: ProductionHistory,
    ) -> ProductionFeatureMatrix:
        panel = FeaturePanel(history)
        first_feature = FEATURE_WARMUP_SESSIONS[family]
        if (
            len(panel.calendar) <= first_feature
            or panel.calendar[first_feature] > DEVELOPMENT_START_REQUIRED
        ):
            raise ProductionInputError("ten_year_development_window_incomplete")
        if panel.calendar[-1] <= DEVELOPMENT_END:
            raise ProductionInputError("prediction_feature_date_not_after_development")
        recipe = recipe_for(family)
        definition = DEFINITION_VERSIONS[family]
        rows: list[ProductionFeatureRow] = []
        for index in range(first_feature, len(panel.calendar)):
            for code in panel.codes:
                features = panel.values(family, code, index)
                for horizon in recipe.horizons:
                    if index + horizon >= len(panel.calendar):
                        continue
                    feature_at = _available_at(panel.calendar[index])
                    label_end = _available_at(panel.calendar[index + horizon])
                    sample_identity = {
                        "model_family": family,
                        "data_snapshot_id": data_snapshot_id,
                        "definition_version": definition,
                        "entity_id": code,
                        "feature_at": feature_at,
                        "horizon_sessions": horizon,
                    }
                    rows.append(
                        ProductionFeatureRow(
                            sample_id="market-model-sample:"
                            + research_hash(sample_identity).removeprefix("sha256:"),
                            entity_id=code,
                            feature_at=feature_at,
                            label_end_at=label_end,
                            label_available_at=label_end,
                            membership_knowledge=(
                                "reconstructed_not_then_known"
                                if history.membership_reconstructed
                                else "known_at_decision"
                            ),
                            horizon_sessions=horizon,
                            features=features,
                            label=panel.label(code, index, horizon),
                        )
                    )
        latest_index = len(panel.calendar) - 1
        inference = tuple(
            ProductionInferenceRow(
                entity_id=code,
                feature_at=_available_at(panel.calendar[latest_index]),
                horizon_sessions=horizon,
                features=panel.values(family, code, latest_index),
            )
            for code in panel.codes
            for horizon in recipe.horizons
        )
        if not rows or not inference:
            raise ProductionInputError("production_feature_matrix_empty")
        return freeze_feature_matrix(
            model_family=family,
            data_snapshot_id=data_snapshot_id,
            definition_version=definition,
            as_of=_available_at(panel.calendar[latest_index]),
            feature_names=panel.feature_names(family),
            rows=tuple(rows),
            inference_rows=inference,
        )


def point_in_time_samples(
    matrix: ProductionFeatureMatrix,
    *,
    horizon: int,
) -> tuple[PointInTimeSample, ...]:
    return tuple(
        PointInTimeSample(
            sample_id=row.sample_id,
            entity_id=row.entity_id,
            feature_at=row.feature_at,
            label_end_at=row.label_end_at,
            label_available_at=row.label_available_at,
            membership_knowledge=row.membership_knowledge,
        )
        for row in matrix.rows
        if row.horizon_sessions == horizon
    )


def training_set(
    matrix: ProductionFeatureMatrix,
    *,
    horizon: int,
    sample_ids: Sequence[str],
) -> TabularTrainingSet:
    indexed = {row.sample_id: row for row in matrix.rows if row.horizon_sessions == horizon}
    missing = tuple(sample_id for sample_id in sample_ids if sample_id not in indexed)
    if missing:
        raise ValueError("training sample identity absent from feature matrix")
    ordered = tuple(indexed[sample_id] for sample_id in sample_ids)
    return TabularTrainingSet(
        sample_ids=tuple(row.sample_id for row in ordered),
        feature_at=tuple(row.feature_at for row in ordered),
        feature_names=matrix.feature_names,
        features=np.asarray(
            [[np.nan if value is None else value for value in row.features] for row in ordered],
            dtype=float,
        ),
        labels=np.asarray([row.label for row in ordered], dtype=float),
    )


def inference_set(
    matrix: ProductionFeatureMatrix,
    *,
    horizon: int,
) -> tuple[tuple[str, ...], np.ndarray]:
    rows = tuple(
        sorted(
            (row for row in matrix.inference_rows if row.horizon_sessions == horizon),
            key=lambda row: row.entity_id,
        )
    )
    if not rows:
        raise ValueError("inference rows are missing for requested horizon")
    return (
        tuple(row.entity_id for row in rows),
        np.asarray(
            [[np.nan if value is None else value for value in row.features] for row in rows],
            dtype=float,
        ),
    )


def _available_at(day: date) -> datetime:
    return datetime.combine(day, time(18), tzinfo=SHANGHAI)


__all__ = [
    "DEFINITION_VERSIONS",
    "DEVELOPMENT_END",
    "FEATURE_WARMUP_SESSIONS",
    "ProductionFeatureMatrixBuilder",
    "inference_set",
    "point_in_time_samples",
    "training_set",
]
