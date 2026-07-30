"""Vector-style panel evaluator and WP-0070 raw-envelope adapter."""

from __future__ import annotations

from math import floor

from ..contracts import CoreInputSnapshot
from ..feature_builder import build_core_raw_feature_envelope
from ..feature_output import CoreRawFeatureEnvelope
from ..feature_values import CoreRawFeatureRowDraft
from ..identity import validate_core_factor_sessions
from ..packages import FORMULAIC_ALPHA101, FORMULAIC_ALPHA101_FEATURE_ORDER
from ..universe import core_universe_content_hash
from .computation import alpha101_computation_manifest_hash
from .inputs import Alpha101Panel
from .operations import (
    binary,
    constant,
    cross_section,
    delay,
    elementwise_call,
    indneutralize,
    rolling,
    rolling_function,
    ternary,
    unary,
)
from .registry import ALPHA101_DEFINITIONS, DEFINITION_VERSION, Alpha101Definition
from .syntax import AstNode, parse_formula
from .values import Matrix

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


class Alpha101Evaluator:
    def __init__(self, panel: Alpha101Panel) -> None:
        self.panel = panel
        self._cache: dict[tuple[object, ...], Matrix] = {}

    def evaluate(self, definition: Alpha101Definition) -> Matrix:
        return self._node(parse_formula(definition.raw_formula))

    def _node(self, node: AstNode) -> Matrix:
        key = node.canonical()
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = self._uncached(node)
        self._cache[key] = result
        return result

    def _uncached(self, node: AstNode) -> Matrix:
        if node.kind == "number":
            return constant(self.panel, float(node.value))
        if node.kind == "identifier":
            return self.panel.input_matrix(node.value)
        if node.kind == "unary":
            return unary(self._node(node.children[0]), node.value)
        if node.kind == "binary":
            return binary(
                self._node(node.children[0]),
                self._node(node.children[1]),
                node.value,
            )
        if node.kind == "ternary":
            return ternary(*(self._node(child) for child in node.children))
        if node.kind != "call":
            raise ValueError(f"unsupported AST kind {node.kind}")
        return self._call(node)

    def _call(self, node: AstNode) -> Matrix:
        name = node.value
        if name == "rank":
            return cross_section(self._node(node.children[0]), self.panel, "rank")
        if name == "scale":
            target = float(node.children[1].value) if len(node.children) == 2 else 1.0
            return cross_section(self._node(node.children[0]), self.panel, "scale", target)
        if name == "indneutralize":
            level = node.children[1].value.removeprefix("indclass.")
            return indneutralize(self._node(node.children[0]), self.panel, level)
        if name == "delay":
            return delay(self._node(node.children[0]), _window(node.children[1]))
        if name == "delta":
            source = self._node(node.children[0])
            return binary(source, delay(source, _window(node.children[1])), "-")
        if name in _ROLLING:
            window = _window(node.children[-1])
            arguments = tuple(self._node(child) for child in node.children[:-1])
            return rolling(arguments, window, rolling_function(name))
        if name in {"min", "max"} and node.children[1].kind == "number":
            source = self._node(node.children[0])
            return rolling((source,), _window(node.children[1]), rolling_function(f"ts_{name}"))
        arguments = tuple(self._node(child) for child in node.children)
        return elementwise_call(name, arguments)


def _window(node: AstNode) -> int:
    if node.kind != "number":
        raise ValueError("Alpha101 time windows must be literal")
    window = floor(float(node.value))
    if window < 1:
        raise ValueError("Alpha101 time windows must floor to at least one session")
    return window


def evaluate_formulaic_alpha101(
    *,
    core_input: CoreInputSnapshot,
    panel: Alpha101Panel,
) -> CoreRawFeatureEnvelope:
    calculation_sessions = validate_core_factor_sessions(core_input, panel.sessions)
    if not panel.sessions or panel.sessions[-1] != core_input.decision_date:
        raise ValueError("Alpha101 panel must end on the CoreInputSnapshot decision date")
    current_decisions = panel.universe_history.current_decisions()
    if (
        panel.universe_history.manifest.universe_version != core_input.universe_version
        or core_universe_content_hash(current_decisions) != core_input.universe_content_hash
    ):
        raise ValueError("Alpha101 current U0 decisions do not match CoreInputSnapshot")
    if panel.universe_history.cutoff(len(panel.sessions) - 1) != core_input.cutoff_at:
        raise ValueError("Alpha101 final U0 cutoff must equal the CoreInputSnapshot cutoff")
    if any(
        panel.universe_history.cutoff(index) > core_input.cutoff_at
        for index in range(len(panel.sessions))
    ):
        raise ValueError("Alpha101 U0 history crosses the CoreInputSnapshot cutoff")
    panel.validate_input_boundaries(core_input)
    evaluator = Alpha101Evaluator(panel)
    final_index = len(panel.sessions) - 1
    final_members = panel.members(final_index)
    rows = []
    for definition in ALPHA101_DEFINITIONS:
        final_values = evaluator.evaluate(definition)[-1]
        for instrument_index, instrument_id in enumerate(panel.instruments):
            if not final_members[instrument_index]:
                continue
            cell = final_values[instrument_index]
            rows.append(
                CoreRawFeatureRowDraft(
                    instrument_id=instrument_id,
                    decision_time=core_input.cutoff_at,
                    feature_definition_id=definition.feature_definition_id,
                    feature_definition_version=DEFINITION_VERSION,
                    value_raw=cell.value,
                    availability_state=cell.state,
                    missing_reason_code=cell.reason.value if cell.reason is not None else None,
                )
            )
    return build_core_raw_feature_envelope(
        core_input=core_input,
        package_spec=FORMULAIC_ALPHA101,
        computation_manifest_hash=alpha101_computation_manifest_hash(),
        calculation_sessions=calculation_sessions,
        feature_order=FORMULAIC_ALPHA101_FEATURE_ORDER,
        rows=rows,
    )


__all__ = ["Alpha101Evaluator", "evaluate_formulaic_alpha101"]
