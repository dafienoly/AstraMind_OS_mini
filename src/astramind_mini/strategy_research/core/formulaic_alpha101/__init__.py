"""Formulaic Alpha101 v3 local fidelity package."""

from .capabilities import L3_CAPABILITY_MANIFEST_HASH
from .computation import ALPHA101_COMPUTATION_MANIFEST_HASH
from .evaluator import Alpha101Evaluator, evaluate_formulaic_alpha101
from .inputs import Alpha101DailyObservation, Alpha101Panel
from .reasons import Alpha101Reason
from .registry import (
    ALPHA101_DEFINITIONS,
    FORMULA_REGISTRY_HASH,
    FORMULA_REGISTRY_VERSION,
    OPERATOR_SEMANTICS_VERSION,
    SOURCE_PDF_SHA256,
    Alpha101Definition,
)
from .universe import (
    Alpha101UniverseHistory,
    Alpha101UniverseHistoryManifest,
    freeze_alpha101_universe_history,
)

__all__ = [
    "ALPHA101_COMPUTATION_MANIFEST_HASH",
    "ALPHA101_DEFINITIONS",
    "FORMULA_REGISTRY_HASH",
    "FORMULA_REGISTRY_VERSION",
    "L3_CAPABILITY_MANIFEST_HASH",
    "OPERATOR_SEMANTICS_VERSION",
    "SOURCE_PDF_SHA256",
    "Alpha101DailyObservation",
    "Alpha101Definition",
    "Alpha101Evaluator",
    "Alpha101Panel",
    "Alpha101Reason",
    "Alpha101UniverseHistory",
    "Alpha101UniverseHistoryManifest",
    "evaluate_formulaic_alpha101",
    "freeze_alpha101_universe_history",
]
