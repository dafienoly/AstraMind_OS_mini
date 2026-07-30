"""AstraMind's canonical 24-dimensional raw formula package."""

from .computation_semantics import (
    F0_FINANCIAL_COMPUTATION_SEMANTICS,
    F0_MARKET_OPERATOR_SEMANTICS,
    F0FinancialComputationSemantics,
    F0MarketOperatorSemantics,
)
from .evaluator import evaluate_astramind_f0
from .inputs import (
    F0CompanyClassification,
    F0CompanyType,
    F0DividendFact,
    F0FinancialFact,
    F0FinancialMetric,
    F0InputBundle,
    F0MarketBar,
    F0StatementKind,
)
from .reasons import F0Reason
from .registry import (
    F0_DEFINITION_REGISTRY_HASH,
    F0_DEFINITIONS,
    F0_FULL_DEFINITION_MANIFEST_HASH,
    F0Definition,
    full_definition_manifest_hash,
    validate_f0_definition_manifest,
)

__all__ = [
    "F0_DEFINITIONS",
    "F0_DEFINITION_REGISTRY_HASH",
    "F0_FINANCIAL_COMPUTATION_SEMANTICS",
    "F0_FULL_DEFINITION_MANIFEST_HASH",
    "F0_MARKET_OPERATOR_SEMANTICS",
    "F0CompanyClassification",
    "F0CompanyType",
    "F0Definition",
    "F0DividendFact",
    "F0FinancialComputationSemantics",
    "F0FinancialFact",
    "F0FinancialMetric",
    "F0InputBundle",
    "F0MarketBar",
    "F0MarketOperatorSemantics",
    "F0Reason",
    "F0StatementKind",
    "evaluate_astramind_f0",
    "full_definition_manifest_hash",
    "validate_f0_definition_manifest",
]
