"""Publish one immutable, unvalidated WP-0062 production result."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path

from ..artifacts import SkopsArtifactStore
from ..contracts import DataGateState, EvidenceWindow, HyperparameterValue
from ..evidence import freeze_evidence_bundle
from ..evidence_store import MarketModelEvidenceStore
from ..identity import freeze_manifest
from ..manifest_store import MarketModelManifestStore
from ..predictions import freeze_prediction_batch
from ..recipes import MarketModelRecipe
from .artifacts import serialize_deterministically
from .contracts import ProductionFeatureMatrix, ProductionRunResult
from .environment import production_dependencies
from .identity import (
    freeze_prediction_publication,
    freeze_run_result,
)
from .source import REQUIRED_DATASETS
from .storage import (
    ProductionFeatureMatrixStore,
    ProductionPredictionStore,
    ProductionRunStore,
)
from .trainer import ProductionModelTrainer, ProductionTrainedBundle


class ProductionArtifactPublisher:
    def __init__(self, output_root: Path) -> None:
        self._trainer = ProductionModelTrainer()
        self._matrix_store = ProductionFeatureMatrixStore(output_root)
        self._prediction_store = ProductionPredictionStore(output_root)
        self._run_store = ProductionRunStore(output_root)
        self._artifacts = SkopsArtifactStore(output_root)
        self._manifests = MarketModelManifestStore(output_root)
        self._evidence = MarketModelEvidenceStore(output_root)

    def publish(
        self,
        *,
        request_id: str,
        scheduled_month: date,
        code_identity: str,
        matrix: ProductionFeatureMatrix,
        trained: ProductionTrainedBundle,
        recipe: MarketModelRecipe,
        cutoff: datetime,
    ) -> ProductionRunResult:
        serialized = serialize_deterministically(trained.estimators)
        self._artifacts.publish(serialized)
        manifest = freeze_manifest(
            recipe=recipe,
            data_snapshot_id=matrix.data_snapshot_id,
            feature_snapshot_id=matrix.feature_snapshot.feature_snapshot_id,
            training_start=trained.training_start,
            training_end=trained.training_end,
            maturity_cutoff=trained.maturity_cutoff,
            feature_names=matrix.feature_names,
            estimator="sklearn.HistGradientBoostingRegressor.multi_horizon",
            hyperparameters=_hyperparameters(trained.parameters),
            code_identity=code_identity,
            dependency_versions=production_dependencies(),
            artifact_hash=serialized.content_hash,
            created_at=matrix.as_of,
        )
        evidence = freeze_evidence_bundle(
            manifest_id=manifest.manifest_id,
            windows=(
                EvidenceWindow(
                    purpose="development",
                    start=trained.training_start,
                    end=trained.training_end,
                ),
            ),
            validations=(),
            data_gates=_data_gates(matrix, trained),
            evidence_state="unvalidated",
            created_at=matrix.as_of,
        )
        regressions = self._trainer.predict(matrix, recipe=recipe, trained=trained)
        batch = freeze_prediction_batch(
            model_family=recipe.family,
            manifest_id=manifest.manifest_id,
            data_snapshot_id=matrix.data_snapshot_id,
            feature_snapshot_id=matrix.feature_snapshot.feature_snapshot_id,
            as_of=matrix.as_of,
            horizons=recipe.horizons,
            evidence_state="unvalidated",
            regressions=regressions,
        )
        publication = freeze_prediction_publication(
            batch=batch,
            baseline_method_version=recipe.baseline_method_version,
            training_cutoff=cutoff,
            maturity_cutoff=cutoff,
            model_artifact_hash=serialized.content_hash,
            feature_content_hash=matrix.content_hash,
        )
        self._matrix_store.publish(matrix)
        self._manifests.publish(manifest)
        self._evidence.publish(evidence)
        self._prediction_store.publish(publication)
        result = freeze_run_result(
            request_id=request_id,
            model_family=recipe.family,
            data_snapshot_id=matrix.data_snapshot_id,
            scheduled_month=scheduled_month,
            state="trained_evidence_insufficient",
            created_at=matrix.as_of,
            reason_codes=("supportive_evidence_not_validated",),
            feature_matrix_id=matrix.matrix_id,
            manifest_id=manifest.manifest_id,
            evidence_bundle_id=evidence.evidence_bundle_id,
            prediction_publication_id=publication.publication_id,
        )
        self._run_store.publish(result)
        return result


def _data_gates(
    matrix: ProductionFeatureMatrix,
    trained: ProductionTrainedBundle,
) -> tuple[DataGateState, ...]:
    return (
        DataGateState(
            gate_name="immutable_snapshot_integrity",
            status="pass",
            observation_count=len(REQUIRED_DATASETS),
            coverage_ratio=1.0,
        ),
        DataGateState(
            gate_name="production_feature_matrix",
            status="pass",
            observation_count=len(matrix.rows),
            coverage_ratio=1.0,
        ),
        DataGateState(
            gate_name="label_maturity",
            status="pass",
            observation_count=trained.mature_sample_count,
            coverage_ratio=1.0,
        ),
        DataGateState(
            gate_name="supportive_evidence",
            status="pending",
            observation_count=0,
            reason_codes=("supportive_evidence_not_validated",),
        ),
    )


def _hyperparameters(
    parameters: Mapping[int, Mapping[str, bool | int | float | str]],
) -> tuple[HyperparameterValue, ...]:
    return tuple(
        HyperparameterValue(name=f"h{horizon}.{name}", value=values[name])
        for horizon in sorted(parameters)
        for name in sorted(parameters[horizon])
        for values in (parameters[horizon],)
    )


__all__ = ["ProductionArtifactPublisher"]
