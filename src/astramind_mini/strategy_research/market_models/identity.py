"""Deterministic identities for model manifests and activations."""

from __future__ import annotations

from datetime import date, datetime

from ..application.identity import research_hash
from .contracts import (
    DependencyVersion,
    EvidenceWindow,
    HyperparameterValue,
    MarketModelManifest,
    ModelActivation,
)
from .recipes import MarketModelRecipe


def freeze_manifest(
    *,
    recipe: MarketModelRecipe,
    data_snapshot_id: str,
    feature_snapshot_id: str,
    training_start: date,
    training_end: date,
    maturity_cutoff: date,
    feature_names: tuple[str, ...],
    estimator: str,
    hyperparameters: tuple[HyperparameterValue, ...],
    code_identity: str,
    dependency_versions: tuple[DependencyVersion, ...],
    artifact_hash: str,
    created_at: datetime,
) -> MarketModelManifest:
    identity = {
        "model_family": recipe.family,
        "method_version": recipe.method_version,
        "baseline_method_version": recipe.baseline_method_version,
        "task": recipe.task,
        "target_definition_version": recipe.target_definition_version,
        "data_snapshot_id": data_snapshot_id,
        "feature_snapshot_id": feature_snapshot_id,
        "training_start": training_start,
        "training_end": training_end,
        "maturity_cutoff": maturity_cutoff,
        "feature_names": feature_names,
        "estimator": estimator,
        "hyperparameters": hyperparameters,
        "random_seed": recipe.random_seed,
        "code_identity": code_identity,
        "dependency_versions": dependency_versions,
        "artifact_hash": artifact_hash,
        "created_at": created_at,
    }
    digest = research_hash(identity).removeprefix("sha256:")
    return MarketModelManifest(
        manifest_id=f"market-model-manifest:{digest}",
        model_family=recipe.family,
        method_version=recipe.method_version,
        baseline_method_version=recipe.baseline_method_version,
        task=recipe.task,
        target_definition_version=recipe.target_definition_version,
        data_snapshot_id=data_snapshot_id,
        feature_snapshot_id=feature_snapshot_id,
        training_window=EvidenceWindow(
            purpose="development",
            start=training_start,
            end=training_end,
        ),
        maturity_cutoff=maturity_cutoff,
        feature_names=feature_names,
        estimator=estimator,
        hyperparameters=hyperparameters,
        random_seed=recipe.random_seed,
        code_identity=code_identity,
        dependency_versions=dependency_versions,
        artifact_hash=artifact_hash,
        created_at=created_at,
    )


def manifest_content_hash(manifest: MarketModelManifest) -> str:
    return research_hash(
        {
            "model_family": manifest.model_family,
            "method_version": manifest.method_version,
            "baseline_method_version": manifest.baseline_method_version,
            "task": manifest.task,
            "target_definition_version": manifest.target_definition_version,
            "data_snapshot_id": manifest.data_snapshot_id,
            "feature_snapshot_id": manifest.feature_snapshot_id,
            "training_start": manifest.training_window.start,
            "training_end": manifest.training_window.end,
            "maturity_cutoff": manifest.maturity_cutoff,
            "feature_names": manifest.feature_names,
            "estimator": manifest.estimator,
            "hyperparameters": manifest.hyperparameters,
            "random_seed": manifest.random_seed,
            "code_identity": manifest.code_identity,
            "dependency_versions": manifest.dependency_versions,
            "artifact_hash": manifest.artifact_hash,
            "created_at": manifest.created_at,
        }
    )


def freeze_activation(
    *,
    model_family: str,
    active_method_version: str,
    fallback_method_version: str,
    state: str,
    effective_at: datetime,
    active_manifest_id: str | None = None,
    evidence_bundle_id: str | None = None,
    reason_codes: tuple[str, ...] = (),
) -> ModelActivation:
    payload = {
        "model_family": model_family,
        "active_method_version": active_method_version,
        "active_manifest_id": active_manifest_id,
        "evidence_bundle_id": evidence_bundle_id,
        "state": state,
        "fallback_method_version": fallback_method_version,
        "reason_codes": reason_codes,
        "effective_at": effective_at,
        "broker_actions_allowed": False,
        "portfolio_targets_allowed": False,
        "order_plans_allowed": False,
    }
    provisional = ModelActivation.model_validate(
        {
            "activation_id": "model-activation:pending",
            **payload,
        }
    )
    digest = activation_content_hash(provisional).removeprefix("sha256:")
    return provisional.model_copy(update={"activation_id": f"model-activation:{digest}"})


def activation_content_hash(activation: ModelActivation) -> str:
    return research_hash(activation.model_dump(mode="json", exclude={"activation_id"}))


__all__ = [
    "activation_content_hash",
    "freeze_activation",
    "freeze_manifest",
    "manifest_content_hash",
]
