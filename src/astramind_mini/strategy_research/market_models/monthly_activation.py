"""Monthly challenger reconciliation for read-only market-model activations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .activation_policy import activation_for_evidence
from .activation_store import ModelActivationStore
from .contracts import (
    MarketModelEvidenceBundle,
    MarketModelManifest,
    ModelActivation,
)
from .evidence_store import MarketModelEvidenceStore
from .identity import freeze_activation
from .manifest_store import MarketModelManifestStore
from .recipes import recipe_for


@dataclass(frozen=True)
class MarketModelCandidate:
    manifest: MarketModelManifest
    evidence: MarketModelEvidenceBundle


@dataclass(frozen=True)
class MonthlyActivationResult:
    model_family: str
    state: str
    activation_id: str | None
    reason_codes: tuple[str, ...]


class MonthlyMarketModelActivationService:
    def __init__(
        self,
        *,
        root: Path,
        artifact_validator: Callable[[str], object],
    ) -> None:
        self._manifests = MarketModelManifestStore(root)
        self._evidence = MarketModelEvidenceStore(root)
        self._activations = ModelActivationStore(root / "activations")
        self._validate_artifact = artifact_validator

    def reconcile(
        self,
        candidates: tuple[MarketModelCandidate, ...],
        *,
        effective_at: datetime,
        allow_unvalidated: bool = False,
    ) -> tuple[MonthlyActivationResult, ...]:
        families = [item.manifest.model_family for item in candidates]
        if len(families) != len(set(families)):
            raise ValueError("月度市场模型候选家族重复")
        return tuple(
            self._reconcile_one(
                candidate,
                effective_at=effective_at,
                allow_unvalidated=allow_unvalidated,
            )
            for candidate in candidates
        )

    def _reconcile_one(
        self,
        candidate: MarketModelCandidate,
        *,
        effective_at: datetime,
        allow_unvalidated: bool,
    ) -> MonthlyActivationResult:
        manifest = candidate.manifest
        recipe = recipe_for(manifest.model_family)
        try:
            current = self._activations.current(manifest.model_family)
        except (FileNotFoundError, ValueError, OSError):
            current = None
        if current is not None and _month(current.effective_at) == _month(effective_at):
            return _result(current, ("monthly_activation_already_recorded",))
        try:
            _validate_recipe(manifest)
            self._validate_artifact(manifest.artifact_hash)
            self._manifests.publish(manifest)
            self._evidence.publish(candidate.evidence)
            activation = activation_for_evidence(
                manifest=manifest,
                evidence=candidate.evidence,
                effective_at=effective_at,
                allow_unvalidated=allow_unvalidated,
            )
        except (FileNotFoundError, ValueError, OSError):
            activation = freeze_activation(
                model_family=recipe.family,
                active_method_version=recipe.baseline_method_version,
                fallback_method_version=recipe.baseline_method_version,
                state="fallback_v1",
                effective_at=effective_at,
                reason_codes=("candidate_integrity_failed",),
            )
        self._activations.publish(activation)
        return _result(activation)


def _validate_recipe(manifest: MarketModelManifest) -> None:
    recipe = recipe_for(manifest.model_family)
    if manifest.method_version != recipe.method_version:
        raise ValueError("市场模型候选方法版本不匹配")
    if manifest.baseline_method_version != recipe.baseline_method_version:
        raise ValueError("市场模型候选基线版本不匹配")
    if manifest.target_definition_version != recipe.target_definition_version:
        raise ValueError("市场模型候选标签版本不匹配")
    if manifest.task != recipe.task:
        raise ValueError("市场模型候选任务类型不匹配")


def _month(value: datetime) -> tuple[int, int]:
    return value.year, value.month


def _result(
    activation: ModelActivation,
    extra_reasons: tuple[str, ...] = (),
) -> MonthlyActivationResult:
    return MonthlyActivationResult(
        model_family=activation.model_family,
        state=activation.state,
        activation_id=activation.activation_id,
        reason_codes=tuple(sorted(set((*activation.reason_codes, *extra_reasons)))),
    )


__all__ = [
    "MarketModelCandidate",
    "MonthlyActivationResult",
    "MonthlyMarketModelActivationService",
]
