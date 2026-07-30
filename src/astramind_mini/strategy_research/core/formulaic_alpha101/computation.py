"""Package-owned computation identity for the Formulaic Alpha101 implementation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from ..packages import FORMULAIC_ALPHA101
from .capabilities import (
    L3_CAPABILITY_MANIFEST_HASH,
    alpha101_l3_capability_manifest,
)
from .input_identity import BAR_SLICE_SEMANTICS, INDUSTRY_SLICE_SEMANTICS
from .registry import (
    ALPHA101_DEFINITIONS,
    AUTHORITATIVE_SOURCE,
    FORMULA_REGISTRY_HASH,
    FORMULA_REGISTRY_VERSION,
    OPERATOR_SEMANTICS_VERSION,
    SOURCE_PDF_BYTES,
    SOURCE_PDF_SHA256,
)
from .universe import HISTORY_MANIFEST_VERSION

COMPUTATION_MANIFEST_VERSION = "formulaic-alpha101-computation-manifest-v1"
EXPRESSION_GRAMMAR_VERSION = "alpha101-expression-grammar-v1"
INPUT_MAPPING_VERSION = "alpha101-core-data-input-mapping-v1"
INDUSTRY_MAPPING_VERSION = "alpha101-sw2021-strict-l1-l2-l3-v1"
_INDUSTRY_LEVELS = ("sector", "industry", "subindustry")
_INPUT_MAPPING = {
    "open_high_low_close": "continuous_research_price_index",
    "returns": "simple_continuous_research_close_return",
    "volume": "point_in_time_raw_shares",
    "vwap": "raw_amount_div_raw_shares_scaled_to_research_close",
    "cap": "point_in_time_total_market_cap_cny",
    "adv": "inclusive_common_session_raw_amount_cny_arithmetic_mean",
}


def alpha101_computation_manifest() -> dict[str, object]:
    """Rebuild the complete package semantics; callers cannot inject a replacement."""
    definitions = [
        {
            "ordinal": item.ordinal,
            "feature_definition_id": item.feature_definition_id,
            "feature_definition_version": item.feature_definition_version,
            "raw_formula": item.raw_formula,
            "raw_decimal_tokens": item.raw_decimal_tokens,
            "canonical_ast": item.canonical_ast,
            "inputs": item.inputs,
            "industry_levels": item.industry_levels,
            "maximum_history_sessions": item.maximum_history_sessions,
            "paper_page": item.paper_page,
        }
        for item in ALPHA101_DEFINITIONS
    ]
    industry_mapping = {
        level: [item.ordinal for item in ALPHA101_DEFINITIONS if level in item.industry_levels]
        for level in _INDUSTRY_LEVELS
    }
    return {
        "manifest_version": COMPUTATION_MANIFEST_VERSION,
        "package_id": FORMULAIC_ALPHA101.package_id,
        "canonical_dimension": FORMULAIC_ALPHA101.canonical_dimension,
        "data_semantics_version": FORMULAIC_ALPHA101.data_semantics_version,
        "universe_version": FORMULAIC_ALPHA101.universe_version,
        "required_definition_registry_hash": (FORMULAIC_ALPHA101.required_definition_registry_hash),
        "authoritative_source": AUTHORITATIVE_SOURCE,
        "source_pdf_sha256": SOURCE_PDF_SHA256,
        "source_pdf_bytes": SOURCE_PDF_BYTES,
        "formula_registry_version": FORMULA_REGISTRY_VERSION,
        "formula_registry_hash": FORMULA_REGISTRY_HASH,
        "operator_semantics_version": OPERATOR_SEMANTICS_VERSION,
        "expression_grammar_version": EXPRESSION_GRAMMAR_VERSION,
        "unary_power_precedence": (
            "power-before-prefix-unary; exponent-right-hand-side-accepts-unary"
        ),
        "pearson_two_point_rule": "exact-delta-sign-with-zero-variance-failure",
        "input_mapping_version": INPUT_MAPPING_VERSION,
        "input_mapping": _INPUT_MAPPING,
        "input_slice_semantics": {
            "bars": BAR_SLICE_SEMANTICS,
            "industry": INDUSTRY_SLICE_SEMANTICS,
            "u0_history": HISTORY_MANIFEST_VERSION,
        },
        "industry_mapping_version": INDUSTRY_MAPPING_VERSION,
        "industry_taxonomy": "SW2021-point-in-time-L1-L2-L3",
        "industry_fallback": "forbidden",
        "l3_capability_manifest": alpha101_l3_capability_manifest(),
        "l3_capability_manifest_hash": L3_CAPABILITY_MANIFEST_HASH,
        "industry_mapping": industry_mapping,
        "definitions": definitions,
    }


def canonical_computation_manifest_hash(manifest: Mapping[str, object]) -> str:
    encoded = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def alpha101_computation_manifest_hash() -> str:
    return canonical_computation_manifest_hash(alpha101_computation_manifest())


ALPHA101_COMPUTATION_MANIFEST_HASH = alpha101_computation_manifest_hash()
EXPECTED_ALPHA101_COMPUTATION_MANIFEST_HASH = (
    "sha256:26625f1b77bd63cc0064207e1612e2916ff99682aa4685807beeff3c735adc61"
)
if ALPHA101_COMPUTATION_MANIFEST_HASH != EXPECTED_ALPHA101_COMPUTATION_MANIFEST_HASH:
    raise ValueError(
        "Alpha101 computation semantics changed without a versioned identity: "
        f"{ALPHA101_COMPUTATION_MANIFEST_HASH}"
    )

__all__ = [
    "ALPHA101_COMPUTATION_MANIFEST_HASH",
    "COMPUTATION_MANIFEST_VERSION",
    "EXPECTED_ALPHA101_COMPUTATION_MANIFEST_HASH",
    "EXPRESSION_GRAMMAR_VERSION",
    "INDUSTRY_MAPPING_VERSION",
    "INPUT_MAPPING_VERSION",
    "alpha101_computation_manifest",
    "alpha101_computation_manifest_hash",
    "canonical_computation_manifest_hash",
]
