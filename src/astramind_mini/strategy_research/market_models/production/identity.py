"""Deterministic identities for WP-0062 production artifacts."""

from __future__ import annotations

from datetime import date, datetime

from astramind_mini.contracts import FeatureSnapshot

from ...application.identity import research_hash
from ..predictions import MarketPredictionBatch
from .contracts import (
    ProductionFamily,
    ProductionFeatureMatrix,
    ProductionFeatureRow,
    ProductionInferenceRow,
    ProductionPipelineState,
    ProductionPredictionPublication,
    ProductionRunResult,
)


def production_request_id(
    *,
    model_family: str,
    data_snapshot_id: str,
    scheduled_month: date,
    code_identity: str,
    dependency_versions: tuple[tuple[str, str], ...],
    parameter_grid: tuple[tuple[tuple[str, bool | int | float | str], ...], ...],
) -> str:
    return research_hash(
        {
            "model_family": model_family,
            "data_snapshot_id": data_snapshot_id,
            "scheduled_month": scheduled_month,
            "code_identity": code_identity,
            "dependency_versions": dependency_versions,
            "parameter_grid": parameter_grid,
        }
    )


def freeze_feature_matrix(
    *,
    model_family: ProductionFamily,
    data_snapshot_id: str,
    definition_version: str,
    as_of: datetime,
    feature_names: tuple[str, ...],
    rows: tuple[ProductionFeatureRow, ...],
    inference_rows: tuple[ProductionInferenceRow, ...],
) -> ProductionFeatureMatrix:
    payload = {
        "model_family": model_family,
        "data_snapshot_id": data_snapshot_id,
        "definition_version": definition_version,
        "as_of": as_of,
        "feature_names": feature_names,
        "rows": rows,
        "inference_rows": inference_rows,
    }
    digest = research_hash(payload)
    suffix = digest.removeprefix("sha256:")
    feature_snapshot = FeatureSnapshot(
        feature_snapshot_id=f"feature-snapshot:{suffix}",
        data_snapshot_id=data_snapshot_id,
        as_of=as_of,
        definition_version=definition_version,
        content_hash=digest,
    )
    return ProductionFeatureMatrix(
        matrix_id=f"market-feature-matrix:{suffix}",
        model_family=model_family,
        data_snapshot_id=data_snapshot_id,
        feature_snapshot=feature_snapshot,
        definition_version=definition_version,
        as_of=as_of,
        feature_names=feature_names,
        rows=rows,
        inference_rows=inference_rows,
        content_hash=digest,
    )


def freeze_prediction_publication(
    *,
    batch: MarketPredictionBatch,
    baseline_method_version: str,
    training_cutoff: datetime,
    maturity_cutoff: datetime,
    model_artifact_hash: str,
    feature_content_hash: str,
) -> ProductionPredictionPublication:
    payload = {
        "batch": batch.model_dump(mode="json"),
        "baseline_method_version": baseline_method_version,
        "training_cutoff": training_cutoff,
        "maturity_cutoff": maturity_cutoff,
        "model_artifact_hash": model_artifact_hash,
        "feature_content_hash": feature_content_hash,
        "evidence_state": "unvalidated",
        "broker_actions_allowed": False,
        "portfolio_targets_allowed": False,
        "order_plans_allowed": False,
    }
    digest = research_hash(payload)
    return ProductionPredictionPublication(
        publication_id="market-prediction-publication:" + digest.removeprefix("sha256:"),
        batch=batch,
        baseline_method_version=baseline_method_version,
        training_cutoff=training_cutoff,
        maturity_cutoff=maturity_cutoff,
        model_artifact_hash=model_artifact_hash,
        feature_content_hash=feature_content_hash,
        content_hash=digest,
    )


def freeze_run_result(
    *,
    request_id: str,
    model_family: str,
    data_snapshot_id: str,
    scheduled_month: date,
    state: ProductionPipelineState,
    created_at: datetime,
    reason_codes: tuple[str, ...],
    feature_matrix_id: str | None = None,
    manifest_id: str | None = None,
    evidence_bundle_id: str | None = None,
    prediction_publication_id: str | None = None,
) -> ProductionRunResult:
    payload = {
        "request_id": request_id,
        "model_family": model_family,
        "data_snapshot_id": data_snapshot_id,
        "scheduled_month": scheduled_month,
        "state": state,
        "created_at": created_at,
        "reason_codes": reason_codes,
        "feature_matrix_id": feature_matrix_id,
        "manifest_id": manifest_id,
        "evidence_bundle_id": evidence_bundle_id,
        "prediction_publication_id": prediction_publication_id,
        "broker_actions_allowed": False,
        "portfolio_targets_allowed": False,
        "order_plans_allowed": False,
    }
    digest = research_hash(payload)
    return ProductionRunResult(
        run_id="market-model-run:" + digest.removeprefix("sha256:"),
        request_id=request_id,
        model_family=model_family,
        data_snapshot_id=data_snapshot_id,
        scheduled_month=scheduled_month,
        state=state,
        created_at=created_at,
        reason_codes=reason_codes,
        feature_matrix_id=feature_matrix_id,
        manifest_id=manifest_id,
        evidence_bundle_id=evidence_bundle_id,
        prediction_publication_id=prediction_publication_id,
        content_hash=digest,
    )


__all__ = [
    "freeze_feature_matrix",
    "freeze_prediction_publication",
    "freeze_run_result",
    "production_request_id",
]
