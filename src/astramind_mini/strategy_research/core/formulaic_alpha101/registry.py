"""Immutable Formulaic Alpha101 v3 definition registry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from math import floor

from ..packages import FORMULAIC_ALPHA101, FORMULAIC_ALPHA101_FEATURE_ORDER
from .syntax import AstNode, decimal_tokens, parse_formula

AUTHORITATIVE_SOURCE = "arxiv-1601.00991v3"
SOURCE_PDF_SHA256 = "1f9c21afe32dcb3ee77b31548acdaea00451fbfa1c0ee10c907867bcc736fce9"
SOURCE_PDF_BYTES = 244_416
OPERATOR_SEMANTICS_VERSION = "alpha101-operator-semantics-v1"
FORMULA_REGISTRY_VERSION = "formulaic-alpha101-v3-registry-v1"
DEFINITION_VERSION = "1.0.0"

_INPUTS = {
    "returns",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "cap",
}
_ALLOWED_ADV = {f"adv{window}" for window in (5, 10, 15, 20, 30, 40, 50, 60, 81, 120, 150, 180)}
_INDUSTRY_IDENTIFIERS = {
    "indclass.sector",
    "indclass.industry",
    "indclass.subindustry",
}
_CALLS = {
    "abs",
    "correlation",
    "covariance",
    "decay_linear",
    "delay",
    "delta",
    "indneutralize",
    "log",
    "max",
    "min",
    "product",
    "rank",
    "scale",
    "sign",
    "signedpower",
    "stddev",
    "sum",
    "ts_argmax",
    "ts_argmin",
    "ts_max",
    "ts_min",
    "ts_rank",
}
_INDUSTRY_FORMULAE = {
    "sector": (58, 67, 76, 79, 82),
    "industry": (59, 63, 69, 70, 80, 87, 89, 91, 93, 97),
    "subindustry": (48, 67, 90, 100),
}
_ROLLING = {
    "correlation",
    "covariance",
    "decay_linear",
    "product",
    "stddev",
    "sum",
    "ts_argmax",
    "ts_argmin",
    "ts_max",
    "ts_min",
    "ts_rank",
}


@dataclass(frozen=True)
class Alpha101Definition:
    ordinal: int
    feature_definition_id: str
    feature_definition_version: str
    raw_formula: str
    raw_decimal_tokens: tuple[str, ...]
    canonical_ast: tuple[object, ...]
    inputs: tuple[str, ...]
    industry_levels: tuple[str, ...]
    maximum_history_sessions: int
    paper_page: int


def _load_formulae() -> tuple[str, ...]:
    resource = files(__package__).joinpath("formulae_v3.json")
    values = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("formulae_v3.json must contain only formula strings")
    return tuple(values)


def _identifiers(node: AstNode) -> set[str]:
    found = {node.value} if node.kind == "identifier" else set()
    for child in node.children:
        found.update(_identifiers(child))
    return found


def _calls(node: AstNode) -> set[str]:
    found = {node.value} if node.kind == "call" else set()
    for child in node.children:
        found.update(_calls(child))
    return found


def _validate_definition_ast(node: AstNode) -> None:
    identifiers = _identifiers(node)
    unknown_identifiers = identifiers - _INPUTS - _ALLOWED_ADV - _INDUSTRY_IDENTIFIERS
    if unknown_identifiers:
        raise ValueError(f"unsupported Alpha101 inputs: {sorted(unknown_identifiers)}")
    unknown_calls = _calls(node) - _CALLS
    if unknown_calls:
        raise ValueError(f"unsupported Alpha101 operators: {sorted(unknown_calls)}")


def _literal_window(node: AstNode) -> int:
    if node.kind != "number":
        raise ValueError("time-series windows must remain literal paper tokens")
    return floor(float(node.value))


def _history(node: AstNode) -> int:
    """Return the largest zero-based common-session lookback offset."""
    child_history = max((_history(child) for child in node.children), default=0)
    if node.kind == "identifier" and node.value.startswith("adv"):
        return int(node.value.removeprefix("adv")) - 1
    if node.kind == "identifier" and node.value == "returns":
        return 1
    if node.kind != "call":
        return child_history
    if node.value in {"delay", "delta"}:
        return _history(node.children[0]) + _literal_window(node.children[1])
    if node.value in _ROLLING:
        return max(_history(child) for child in node.children[:-1]) + (
            _literal_window(node.children[-1]) - 1
        )
    if node.value in {"min", "max"} and node.children[1].kind == "number":
        return _history(node.children[0]) + _literal_window(node.children[1]) - 1
    return child_history


def _paper_page(ordinal: int) -> int:
    for end, page in ((7, 8), (24, 9), (43, 10), (60, 11), (73, 12), (86, 13), (97, 14)):
        if ordinal <= end:
            return page
    return 15


def _levels(ordinal: int) -> tuple[str, ...]:
    return tuple(level for level, ordinals in _INDUSTRY_FORMULAE.items() if ordinal in ordinals)


def _build_registry() -> tuple[Alpha101Definition, ...]:
    formulae = _load_formulae()
    if len(formulae) != 101:
        raise ValueError("Formulaic Alpha101 registry must contain exactly 101 formulae")
    definitions = []
    for ordinal, (feature_id, formula) in enumerate(
        zip(FORMULAIC_ALPHA101_FEATURE_ORDER, formulae, strict=True),
        start=1,
    ):
        ast = parse_formula(formula)
        _validate_definition_ast(ast)
        identifiers = _identifiers(ast)
        inputs = tuple(sorted(identifier for identifier in identifiers if identifier in _INPUTS))
        inputs += tuple(
            sorted(identifier for identifier in identifiers if identifier.startswith("adv"))
        )
        definitions.append(
            Alpha101Definition(
                ordinal=ordinal,
                feature_definition_id=feature_id,
                feature_definition_version=DEFINITION_VERSION,
                raw_formula=formula,
                raw_decimal_tokens=decimal_tokens(formula),
                canonical_ast=ast.canonical(),
                inputs=inputs,
                industry_levels=_levels(ordinal),
                maximum_history_sessions=_history(ast) + 1,
                paper_page=_paper_page(ordinal),
            )
        )
    return tuple(definitions)


ALPHA101_DEFINITIONS = _build_registry()


def _registry_hash() -> str:
    payload = {
        "authoritative_source": AUTHORITATIVE_SOURCE,
        "source_pdf_sha256": SOURCE_PDF_SHA256,
        "source_pdf_bytes": SOURCE_PDF_BYTES,
        "operator_semantics_version": OPERATOR_SEMANTICS_VERSION,
        "formula_registry_version": FORMULA_REGISTRY_VERSION,
        "definitions": [item.__dict__ for item in ALPHA101_DEFINITIONS],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


FORMULA_REGISTRY_HASH = _registry_hash()
EXPECTED_FORMULA_REGISTRY_HASH = (
    "sha256:b2c9dcbeb8c81449cc2e60227aaf87da17a58bb51a04d0eca2468c594fa34a5c"
)

if tuple(item.feature_definition_id for item in ALPHA101_DEFINITIONS) != (
    FORMULAIC_ALPHA101_FEATURE_ORDER
):
    raise ValueError("Alpha101 definition order drifted from WP-0070")
if FORMULAIC_ALPHA101.required_definition_registry_hash != (
    "sha256:6895ebea945ed4c95e43d8fd7d19cd97a77fb3a32f7868133c320a5f9ebde1c5"
):
    raise ValueError("Alpha101 public definition registry hash drifted")
if FORMULA_REGISTRY_HASH != EXPECTED_FORMULA_REGISTRY_HASH:
    raise ValueError("Alpha101 v3 formula registry changed without a versioned identity")

__all__ = [
    "ALPHA101_DEFINITIONS",
    "AUTHORITATIVE_SOURCE",
    "DEFINITION_VERSION",
    "EXPECTED_FORMULA_REGISTRY_HASH",
    "FORMULA_REGISTRY_HASH",
    "FORMULA_REGISTRY_VERSION",
    "OPERATOR_SEMANTICS_VERSION",
    "SOURCE_PDF_BYTES",
    "SOURCE_PDF_SHA256",
    "Alpha101Definition",
]
