"""Immutable contracts for read-only market-model training and activation."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

MarketModelFamily = Literal[
    "industry_heat",
    "industry_rotation",
    "industry_lifecycle",
    "industry_research_ranking",
    "etf_rotation",
]
EvidenceState = Literal[
    "development_only",
    "unvalidated",
    "supported",
    "unsupported",
    "blocked",
]
ValidationDecision = Literal["pass", "fail", "blocked"]
ActivationState = Literal["active_v2", "unvalidated_v2", "fallback_v1", "blocked"]
DataGateStatus = Literal["pass", "fail", "pending", "not_applicable"]


class EvidenceWindow(ContractModel):
    """One named point-in-time evidence interval."""

    purpose: Literal["development", "sealed_replay", "audit", "prospective"]
    start: date
    end: date

    @model_validator(mode="after")
    def validate_dates(self) -> EvidenceWindow:
        if self.start > self.end:
            raise ValueError("evidence window start must not be after end")
        return self


class HyperparameterValue(ContractModel):
    """Stable, JSON-safe hyperparameter representation."""

    name: Identifier
    value: bool | int | float | str


class DependencyVersion(ContractModel):
    package: Identifier
    version: Version


class MarketModelManifest(ContractModel):
    """Exact identity of one trained read-only market model."""

    manifest_id: Identifier
    model_family: MarketModelFamily
    method_version: Version
    baseline_method_version: Version
    task: Literal["regression", "classification"]
    target_definition_version: Version
    data_snapshot_id: Identifier
    feature_snapshot_id: Identifier
    training_window: EvidenceWindow
    maturity_cutoff: date
    feature_names: tuple[Identifier, ...] = Field(min_length=1)
    estimator: Identifier
    hyperparameters: tuple[HyperparameterValue, ...] = ()
    random_seed: int = Field(ge=0)
    code_identity: Identifier
    dependency_versions: tuple[DependencyVersion, ...] = Field(min_length=1)
    artifact_hash: ContentHash
    created_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_manifest(self) -> MarketModelManifest:
        if self.training_window.purpose != "development":
            raise ValueError("training_window must use the development purpose")
        if self.maturity_cutoff > self.training_window.end:
            raise ValueError("maturity_cutoff must not be after training window end")
        if len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature_names must be unique and ordered")
        parameter_names = [item.name for item in self.hyperparameters]
        if len(set(parameter_names)) != len(parameter_names):
            raise ValueError("hyperparameter names must be unique")
        return self


class ModelValidationSummary(ContractModel):
    """One metric and its non-performance safety gates."""

    validation_id: Identifier
    manifest_id: Identifier
    window: EvidenceWindow
    metric_name: Identifier
    candidate_value: float | None = None
    reference_value: float | None = None
    bootstrap_lower_bound: float | None = None
    subperiods_supporting: int = Field(ge=0)
    subperiods_total: int = Field(ge=0)
    coverage_not_worse: bool
    risk_not_worse: bool
    turnover_not_worse: bool
    cost_not_worse: bool
    decision: ValidationDecision
    reason_codes: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_summary(self) -> ModelValidationSummary:
        if self.window.purpose not in {"sealed_replay", "audit", "prospective"}:
            raise ValueError("validation window cannot be a development window")
        if self.subperiods_supporting > self.subperiods_total:
            raise ValueError("supporting subperiods cannot exceed total")
        gates_pass = (
            self.coverage_not_worse
            and self.risk_not_worse
            and self.turnover_not_worse
            and self.cost_not_worse
        )
        if self.decision == "pass" and not gates_pass:
            raise ValueError("validation cannot pass when a safety gate is worse")
        if self.decision != "pass" and not self.reason_codes:
            raise ValueError("failed or blocked validation requires reason codes")
        return self


class DataGateState(ContractModel):
    gate_name: Identifier
    status: DataGateStatus
    observation_count: int = Field(ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_codes: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_gate(self) -> DataGateState:
        if self.status in {"fail", "pending"} and not self.reason_codes:
            raise ValueError("failed or pending data gate requires reason codes")
        return self


class MarketModelEvidenceBundle(ContractModel):
    """Immutable evidence attached to one exact market model."""

    evidence_bundle_id: Identifier
    manifest_id: Identifier
    windows: tuple[EvidenceWindow, ...] = Field(min_length=1)
    validations: tuple[ModelValidationSummary, ...] = ()
    data_gates: tuple[DataGateState, ...] = ()
    evidence_state: EvidenceState
    content_hash: ContentHash
    created_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_evidence(self) -> MarketModelEvidenceBundle:
        purposes = [window.purpose for window in self.windows]
        if len(set(purposes)) != len(purposes):
            raise ValueError("evidence window purposes must be unique")
        if any(item.manifest_id != self.manifest_id for item in self.validations):
            raise ValueError("validation manifest must match evidence manifest")
        if self.evidence_state == "supported":
            if not self.validations or any(item.decision != "pass" for item in self.validations):
                raise ValueError("supported evidence requires only passing validations")
            if any(item.status not in {"pass", "not_applicable"} for item in self.data_gates):
                raise ValueError("supported evidence requires all applicable data gates to pass")
        return self


class ModelActivation(ContractModel):
    """Read-only method pointer; never a strategy promotion."""

    activation_id: Identifier
    model_family: MarketModelFamily
    active_method_version: Version
    active_manifest_id: Identifier | None = None
    evidence_bundle_id: Identifier | None = None
    state: ActivationState
    fallback_method_version: Version
    reason_codes: tuple[Identifier, ...] = ()
    effective_at: AwareDatetime
    broker_actions_allowed: Literal[False] = False
    portfolio_targets_allowed: Literal[False] = False
    order_plans_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_activation(self) -> ModelActivation:
        v2_state = self.state in {"active_v2", "unvalidated_v2"}
        if v2_state and (self.active_manifest_id is None or self.evidence_bundle_id is None):
            raise ValueError("v2 activation requires manifest and evidence identities")
        if self.state in {"fallback_v1", "blocked"} and not self.reason_codes:
            raise ValueError("fallback or blocked activation requires reason codes")
        if (
            self.state == "fallback_v1"
            and self.active_method_version != self.fallback_method_version
        ):
            raise ValueError("fallback activation must expose the fallback method")
        return self


class ModelPredictionContext(ContractModel):
    """Model lineage attached to one Market Regime projection."""

    model_family: MarketModelFamily
    method_version: Version
    manifest_id: Identifier | None = None
    prediction_batch_id: Identifier | None = None
    data_snapshot_id: Identifier
    feature_snapshot_id: Identifier | None = None
    as_of: AwareDatetime
    horizon_sessions: int = Field(ge=1)
    evidence_state: EvidenceState
    activation_state: ActivationState
    fallback_reason_codes: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_context(self) -> ModelPredictionContext:
        if self.activation_state in {"active_v2", "unvalidated_v2"} and (
            self.manifest_id is None or self.prediction_batch_id is None
        ):
            raise ValueError("v2 prediction context requires manifest and batch identities")
        if self.activation_state == "fallback_v1" and not self.fallback_reason_codes:
            raise ValueError("fallback prediction context requires reasons")
        return self


__all__ = [
    "ActivationState",
    "DataGateState",
    "DataGateStatus",
    "DependencyVersion",
    "EvidenceState",
    "EvidenceWindow",
    "HyperparameterValue",
    "MarketModelEvidenceBundle",
    "MarketModelFamily",
    "MarketModelManifest",
    "ModelActivation",
    "ModelPredictionContext",
    "ModelValidationSummary",
    "ValidationDecision",
]
