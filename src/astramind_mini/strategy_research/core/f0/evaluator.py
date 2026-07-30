"""Public astramind-f0-v1 evaluator."""

from __future__ import annotations

from ..feature_builder import build_core_raw_feature_envelope
from ..feature_output import CoreRawFeatureEnvelope
from ..feature_values import CoreRawFeatureRowDraft
from ..packages import ASTRAMIND_F0, ASTRAMIND_F0_FEATURE_ORDER
from .financials import evaluate_financial_features
from .inputs import F0InputBundle, validate_f0_input_binding
from .market import evaluate_market_features
from .registry import F0_DEFINITIONS, validate_f0_definition_manifest
from .result import FormulaResult


def evaluate_astramind_f0(bundle: F0InputBundle) -> CoreRawFeatureEnvelope:
    """Evaluate the canonical 24 raw formulas for current U0 research members."""
    validate_f0_input_binding(bundle)
    computation_manifest_hash = validate_f0_definition_manifest(F0_DEFINITIONS)
    instruments = sorted(
        {
            item.instrument_id
            for item in bundle.universe_decisions
            if item.decision_date == bundle.core_input.decision_date and item.research_member
        }
    )
    rows: list[CoreRawFeatureRowDraft] = []
    for instrument_id in instruments:
        results = evaluate_financial_features(bundle, instrument_id)
        results.update(evaluate_market_features(bundle, instrument_id))
        rows.extend(
            _draft(bundle, instrument_id, feature_id, results[feature_id])
            for feature_id in ASTRAMIND_F0_FEATURE_ORDER
        )
    return build_core_raw_feature_envelope(
        core_input=bundle.core_input,
        package_spec=ASTRAMIND_F0,
        computation_manifest_hash=computation_manifest_hash,
        calculation_sessions=bundle.common_sessions,
        feature_order=ASTRAMIND_F0_FEATURE_ORDER,
        rows=rows,
    )


def _draft(
    bundle: F0InputBundle,
    instrument_id: str,
    feature_id: str,
    result: FormulaResult,
) -> CoreRawFeatureRowDraft:
    definition = next(item for item in F0_DEFINITIONS if item.feature_definition_id == feature_id)
    return CoreRawFeatureRowDraft(
        instrument_id=instrument_id,
        decision_time=bundle.core_input.cutoff_at,
        feature_definition_id=feature_id,
        feature_definition_version=definition.feature_definition_version,
        value_raw=result.value,
        availability_state=result.state,
        missing_reason_code=result.reason.value if result.reason is not None else None,
    )


__all__ = ["evaluate_astramind_f0"]
