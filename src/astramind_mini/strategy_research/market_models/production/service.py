"""WP-0062 stage-one orchestration without activation or execution side effects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from ..recipes import COMMON_GRID, MarketModelRecipe, recipe_for
from .contracts import (
    ProductionFamily,
    ProductionFeatureMatrix,
    ProductionPipelineState,
    ProductionRunResult,
)
from .environment import production_dependency_identity
from .identity import freeze_run_result, production_request_id
from .integrity import ProductionOutputVerifier
from .matrix import DEVELOPMENT_END, ProductionFeatureMatrixBuilder
from .publisher import ProductionArtifactPublisher
from .snapshot import ProductionInputError, VerifiedSnapshotReader
from .source import REQUIRED_DATASETS, ProductionHistoryReader
from .storage import ProductionRunStore
from .trainer import (
    ProductionModelTrainer,
    ProductionTrainedBundle,
    canonical_parameter_grid,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
SUPPORTED_FAMILIES = frozenset({"industry_heat", "industry_rotation"})


@dataclass(frozen=True)
class _PreparedRun:
    matrix: ProductionFeatureMatrix
    trained: ProductionTrainedBundle
    recipe: MarketModelRecipe
    cutoff: datetime


class ProductionMarketModelService:
    def __init__(
        self,
        *,
        data_root: Path,
        output_root: Path,
        parameter_grid: Sequence[Mapping[str, bool | int | float | str]] = COMMON_GRID,
    ) -> None:
        self._snapshot = VerifiedSnapshotReader(data_root)
        self._history = ProductionHistoryReader()
        self._matrix_builder = ProductionFeatureMatrixBuilder()
        self._trainer = ProductionModelTrainer()
        self._run_store = ProductionRunStore(output_root)
        self._outputs = ProductionOutputVerifier(output_root)
        self._publisher = ProductionArtifactPublisher(output_root)
        self._grid = tuple(parameter_grid)
        if not self._grid:
            raise ValueError("production parameter grid cannot be empty")

    def run(
        self,
        *,
        model_family: str,
        data_snapshot_id: str,
        scheduled_month: date,
        code_identity: str,
    ) -> ProductionRunResult:
        if scheduled_month.day != 1:
            raise ValueError("scheduled_month must be the first day of a month")
        request_id = self._request_id(
            model_family, data_snapshot_id, scheduled_month, code_identity
        )
        default_created_at = datetime.combine(scheduled_month, time(), tzinfo=SHANGHAI)
        existing = self._existing_result(
            request_id=request_id,
            model_family=model_family,
            data_snapshot_id=data_snapshot_id,
            scheduled_month=scheduled_month,
            created_at=default_created_at,
        )
        if existing is not None:
            return existing
        if model_family not in SUPPORTED_FAMILIES:
            return self._publish_blocked(
                request_id=request_id,
                model_family=model_family,
                data_snapshot_id=data_snapshot_id,
                scheduled_month=scheduled_month,
                created_at=default_created_at,
                state="production_pipeline_unavailable",
                reason_codes=("family_not_in_wp0062_stage_one",),
            )
        try:
            prepared = self._prepare(
                model_family=model_family,
                data_snapshot_id=data_snapshot_id,
                scheduled_month=scheduled_month,
            )
        except ProductionInputError as error:
            return self._publish_blocked(
                request_id=request_id,
                model_family=model_family,
                data_snapshot_id=data_snapshot_id,
                scheduled_month=scheduled_month,
                created_at=default_created_at,
                state="training_data_blocked",
                reason_codes=(error.reason_code,),
            )
        except (ValueError, OSError, duckdb.Error):
            return self._publish_blocked(
                request_id=request_id,
                model_family=model_family,
                data_snapshot_id=data_snapshot_id,
                scheduled_month=scheduled_month,
                created_at=default_created_at,
                state="training_data_blocked",
                reason_codes=("production_matrix_or_training_invalid",),
            )
        try:
            return self._publisher.publish(
                request_id=request_id,
                scheduled_month=scheduled_month,
                code_identity=code_identity,
                matrix=prepared.matrix,
                trained=prepared.trained,
                recipe=prepared.recipe,
                cutoff=prepared.cutoff,
            )
        except (FileNotFoundError, ValueError, OSError):
            return freeze_run_result(
                request_id=request_id,
                model_family=model_family,
                data_snapshot_id=data_snapshot_id,
                scheduled_month=scheduled_month,
                state="artifact_incompatible",
                created_at=prepared.matrix.as_of,
                reason_codes=("production_artifact_publication_failed",),
            )

    def _existing_result(
        self,
        *,
        request_id: str,
        model_family: str,
        data_snapshot_id: str,
        scheduled_month: date,
        created_at: datetime,
    ) -> ProductionRunResult | None:
        try:
            return self._outputs.for_request(request_id)
        except (ValueError, OSError):
            return freeze_run_result(
                request_id=request_id,
                model_family=model_family,
                data_snapshot_id=data_snapshot_id,
                scheduled_month=scheduled_month,
                state="artifact_incompatible",
                created_at=created_at,
                reason_codes=("production_request_record_incompatible",),
            )

    def _request_id(
        self,
        model_family: str,
        data_snapshot_id: str,
        scheduled_month: date,
        code_identity: str,
    ) -> str:
        return production_request_id(
            model_family=model_family,
            data_snapshot_id=data_snapshot_id,
            scheduled_month=scheduled_month,
            code_identity=code_identity,
            dependency_versions=production_dependency_identity(),
            parameter_grid=canonical_parameter_grid(self._grid),
        )

    def _prepare(
        self,
        model_family: str,
        data_snapshot_id: str,
        *,
        scheduled_month: date,
    ) -> _PreparedRun:
        verified = self._snapshot.load(
            data_snapshot_id,
            required_datasets=REQUIRED_DATASETS,
        )
        if verified.snapshot.as_of.date() >= _next_month(scheduled_month):
            raise ProductionInputError("data_snapshot_after_scheduled_month")
        family = _production_family(model_family)
        matrix = self._matrix_builder.build(
            family=family,
            data_snapshot_id=data_snapshot_id,
            history=self._history.load(verified),
        )
        cutoff = datetime.combine(DEVELOPMENT_END, time(18), tzinfo=SHANGHAI)
        recipe = recipe_for(family)
        trained = self._trainer.train(
            matrix,
            recipe=recipe,
            maturity_cutoff=cutoff,
            parameter_grid=self._grid,
        )
        return _PreparedRun(
            matrix=matrix,
            trained=trained,
            recipe=recipe,
            cutoff=cutoff,
        )

    def _publish_blocked(
        self,
        *,
        request_id: str,
        model_family: str,
        data_snapshot_id: str,
        scheduled_month: date,
        created_at: datetime,
        state: ProductionPipelineState,
        reason_codes: tuple[str, ...],
    ) -> ProductionRunResult:
        result = freeze_run_result(
            request_id=request_id,
            model_family=model_family,
            data_snapshot_id=data_snapshot_id,
            scheduled_month=scheduled_month,
            state=state,
            created_at=created_at,
            reason_codes=reason_codes,
        )
        self._run_store.publish(result)
        return result


def _production_family(value: str) -> ProductionFamily:
    if value == "industry_heat":
        return "industry_heat"
    if value == "industry_rotation":
        return "industry_rotation"
    raise ValueError("unsupported production family")


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


__all__ = ["SUPPORTED_FAMILIES", "ProductionMarketModelService"]
