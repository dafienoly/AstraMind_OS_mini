"""Fail-closed verification for previously published production runs."""

from __future__ import annotations

from pathlib import Path

from ..artifacts import SkopsArtifactStore
from ..contracts import MarketModelEvidenceBundle, MarketModelManifest
from ..evidence_store import MarketModelEvidenceStore
from ..manifest_store import MarketModelManifestStore
from ..recipes import recipe_for
from .contracts import (
    ProductionFamily,
    ProductionFeatureMatrix,
    ProductionPredictionPublication,
    ProductionRunResult,
)
from .identity import freeze_run_result
from .matrix import DEFINITION_VERSIONS, DEVELOPMENT_END
from .storage import (
    ProductionFeatureMatrixStore,
    ProductionPredictionStore,
    ProductionRunStore,
)


class ProductionOutputVerifier:
    def __init__(self, output_root: Path) -> None:
        self._matrix_store = ProductionFeatureMatrixStore(output_root)
        self._prediction_store = ProductionPredictionStore(output_root)
        self._run_store = ProductionRunStore(output_root)
        self._artifacts = SkopsArtifactStore(output_root)
        self._manifests = MarketModelManifestStore(output_root)
        self._evidence = MarketModelEvidenceStore(output_root)

    def for_request(self, request_id: str) -> ProductionRunResult | None:
        try:
            result = self._run_store.for_request(request_id)
        except FileNotFoundError:
            return None
        except (ValueError, OSError):
            raise ValueError(f"production request record is incompatible: {request_id}") from None
        if result.state != "trained_evidence_insufficient":
            return result
        try:
            matrix = self._matrix_store.load(_required(result.feature_matrix_id))
            manifest = self._manifests.load(_required(result.manifest_id))
            evidence = self._evidence.load(_required(result.evidence_bundle_id))
            publication = self._prediction_store.load(_required(result.prediction_publication_id))
            family = _production_family(result.model_family)
            recipe = recipe_for(family)
            model = self._artifacts.load(manifest.artifact_hash)
            if not isinstance(model, dict) or set(model) != {
                str(horizon) for horizon in recipe.horizons
            }:
                raise ValueError("production model horizons disagree")
            if not _references_match(
                result=result,
                matrix=matrix,
                manifest=manifest,
                evidence=evidence,
                publication=publication,
                family=family,
            ):
                raise ValueError("production run references disagree")
        except (FileNotFoundError, ValueError, OSError):
            return freeze_run_result(
                request_id=result.request_id,
                model_family=result.model_family,
                data_snapshot_id=result.data_snapshot_id,
                scheduled_month=result.scheduled_month,
                state="artifact_incompatible",
                created_at=result.created_at,
                reason_codes=("production_artifact_integrity_failed",),
            )
        return result


def _references_match(
    *,
    result: ProductionRunResult,
    matrix: ProductionFeatureMatrix,
    manifest: MarketModelManifest,
    evidence: MarketModelEvidenceBundle,
    publication: ProductionPredictionPublication,
    family: ProductionFamily,
) -> bool:
    recipe = recipe_for(family)
    return all(
        (
            matrix.model_family == result.model_family,
            manifest.model_family == result.model_family,
            publication.batch.model_family == result.model_family,
            matrix.data_snapshot_id == result.data_snapshot_id,
            manifest.data_snapshot_id == result.data_snapshot_id,
            publication.batch.data_snapshot_id == result.data_snapshot_id,
            manifest.feature_snapshot_id == matrix.feature_snapshot.feature_snapshot_id,
            publication.batch.feature_snapshot_id == matrix.feature_snapshot.feature_snapshot_id,
            evidence.manifest_id == manifest.manifest_id,
            publication.batch.manifest_id == manifest.manifest_id,
            publication.model_artifact_hash == manifest.artifact_hash,
            publication.feature_content_hash == matrix.content_hash,
            matrix.definition_version == DEFINITION_VERSIONS[family],
            manifest.method_version == recipe.method_version,
            manifest.baseline_method_version == recipe.baseline_method_version,
            manifest.target_definition_version == recipe.target_definition_version,
            manifest.feature_names == matrix.feature_names,
            manifest.training_window.end == DEVELOPMENT_END,
            manifest.maturity_cutoff == DEVELOPMENT_END,
            publication.training_cutoff.date() == DEVELOPMENT_END,
            publication.maturity_cutoff.date() == DEVELOPMENT_END,
            publication.batch.horizons == recipe.horizons,
            evidence.evidence_state == "unvalidated",
        )
    )


def _production_family(value: str) -> ProductionFamily:
    if value == "industry_heat":
        return "industry_heat"
    if value == "industry_rotation":
        return "industry_rotation"
    raise ValueError("unsupported production family")


def _required(value: str | None) -> str:
    if value is None:
        raise ValueError("production run reference is missing")
    return value


__all__ = ["ProductionOutputVerifier"]
