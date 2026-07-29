"""Public building blocks for read-only market research models."""

from .activation_policy import activation_for_evidence
from .activation_store import ModelActivationStore
from .artifacts import SkopsArtifactStore
from .contracts import (
    DataGateState,
    DependencyVersion,
    EvidenceWindow,
    HyperparameterValue,
    MarketModelEvidenceBundle,
    MarketModelManifest,
    ModelActivation,
    ModelPredictionContext,
    ModelValidationSummary,
)
from .evidence import freeze_evidence_bundle
from .evidence_store import MarketModelEvidenceStore
from .integrity import MarketModelIntegrityVerifier
from .manifest_store import MarketModelManifestStore
from .monthly_activation import (
    MarketModelCandidate,
    MonthlyActivationResult,
    MonthlyMarketModelActivationService,
)
from .predictions import (
    ClassificationPrediction,
    ClassProbability,
    MarketPredictionBatch,
    RegressionPrediction,
    freeze_prediction_batch,
)
from .recipes import MarketModelRecipe, market_model_catalog
from .validation import (
    EtfEvidence,
    LifecycleEvidence,
    SafetyGates,
    block_bootstrap_mean,
    validate_etf,
    validate_lifecycle,
    validate_rank_series,
)

__all__ = [
    "ClassProbability",
    "ClassificationPrediction",
    "DataGateState",
    "DependencyVersion",
    "EtfEvidence",
    "EvidenceWindow",
    "HyperparameterValue",
    "LifecycleEvidence",
    "MarketModelCandidate",
    "MarketModelEvidenceBundle",
    "MarketModelEvidenceStore",
    "MarketModelIntegrityVerifier",
    "MarketModelManifest",
    "MarketModelManifestStore",
    "MarketModelRecipe",
    "MarketPredictionBatch",
    "ModelActivation",
    "ModelActivationStore",
    "ModelPredictionContext",
    "ModelValidationSummary",
    "MonthlyActivationResult",
    "MonthlyMarketModelActivationService",
    "RegressionPrediction",
    "SafetyGates",
    "SkopsArtifactStore",
    "activation_for_evidence",
    "block_bootstrap_mean",
    "freeze_evidence_bundle",
    "freeze_prediction_batch",
    "market_model_catalog",
    "validate_etf",
    "validate_lifecycle",
    "validate_rank_series",
]
