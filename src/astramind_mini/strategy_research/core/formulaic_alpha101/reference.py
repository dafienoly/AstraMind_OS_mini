"""Independent cell-at-a-time reference evaluator used by golden fixtures."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from importlib.resources import files
from math import floor, prod

from .inputs import Alpha101Panel
from .reasons import Alpha101Failure, Alpha101Reason
from .registry import Alpha101Definition
from .scalar_operators import (
    average_rank,
    correlation,
    covariance,
    decay_linear,
    divide,
    finite,
    first_extreme_position,
    logarithm,
    power,
    scale,
    signed_power,
    stddev,
    time_series_rank,
)
from .syntax import AstNode, parse_formula
from .values import Alpha101Cell, missing

_N_A_REASONS = {
    Alpha101Reason.SW_L1_NOT_POINT_IN_TIME,
    Alpha101Reason.SW_L2_NOT_POINT_IN_TIME,
    Alpha101Reason.SW_L3_UNAVAILABLE,
}
SCALAR_REFERENCE_GENERATOR_VERSION = "alpha101-scalar-reference-v2"
_REFERENCE_SOURCE_FILES = (
    "inputs.py",
    "input_identity.py",
    "reasons.py",
    "reference.py",
    "scalar_operators.py",
    "syntax.py",
    "universe.py",
    "values.py",
)


def scalar_reference_source_hash() -> str:
    digest = hashlib.sha256()
    package = files(__package__)
    for name in _REFERENCE_SOURCE_FILES:
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(package.joinpath(name).read_bytes())
    return "sha256:" + digest.hexdigest()


class ScalarReferenceEvaluator:
    def __init__(self, panel: Alpha101Panel) -> None:
        self.panel = panel
        self._cache: dict[tuple[tuple[object, ...], int, int], Alpha101Cell] = {}
        self._inputs: dict[str, tuple[tuple[Alpha101Cell, ...], ...]] = {}

    def evaluate(
        self,
        definition: Alpha101Definition,
        *,
        session_index: int,
        instrument_index: int,
    ) -> Alpha101Cell:
        return self._cell(parse_formula(definition.raw_formula), session_index, instrument_index)

    def _cell(self, node: AstNode, session: int, instrument: int) -> Alpha101Cell:
        key = node.canonical(), session, instrument
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = self._uncached(node, session, instrument)
        self._cache[key] = result
        return result

    def _uncached(self, node: AstNode, session: int, instrument: int) -> Alpha101Cell:
        if node.kind == "number":
            return Alpha101Cell(float(node.value))
        if node.kind == "identifier":
            matrix = self._inputs.setdefault(node.value, self.panel.input_matrix(node.value))
            return matrix[session][instrument]
        if node.kind == "unary":
            cell = self._cell(node.children[0], session, instrument)
            return self._apply(lambda value: value if node.value == "+" else -value, cell)
        if node.kind == "binary":
            return self._binary(node, session, instrument)
        if node.kind == "ternary":
            condition = self._cell(node.children[0], session, instrument)
            if condition.reason is not None:
                return condition
            branch = node.children[1] if condition.value != 0 else node.children[2]
            return self._cell(branch, session, instrument)
        if node.kind == "call":
            return self._call(node, session, instrument)
        raise ValueError(f"unsupported AST kind {node.kind}")

    def _binary(self, node: AstNode, session: int, instrument: int) -> Alpha101Cell:
        left = self._cell(node.children[0], session, instrument)
        if node.value == "||" and left.reason is None and left.value != 0:
            return Alpha101Cell(1.0)
        right = self._cell(node.children[1], session, instrument)
        if node.value == "||":
            if left.reason is None:
                return right if right.reason is not None else Alpha101Cell(float(right.value != 0))
            if right.reason is None and right.value != 0:
                return Alpha101Cell(1.0)
            return _preferred_failure(left, right)
        if left.reason is not None or right.reason is not None:
            return _preferred_failure(left, right)
        if left.value is None or right.value is None:
            return missing(Alpha101Reason.INPUT_MISSING)
        functions: dict[str, Callable[[float, float], float]] = {
            "+": lambda x, y: finite(x + y),
            "-": lambda x, y: finite(x - y),
            "*": lambda x, y: finite(x * y),
            "/": divide,
            "^": power,
            "<": lambda x, y: float(x < y),
            ">": lambda x, y: float(x > y),
            "==": lambda x, y: float(x == y),
        }
        left_value = left.value
        right_value = right.value
        return self._attempt(lambda: functions[node.value](left_value, right_value))

    def _call(self, node: AstNode, session: int, instrument: int) -> Alpha101Cell:
        name = node.value
        if name in {"rank", "scale"}:
            return self._cross(node, session, instrument)
        if name == "indneutralize":
            return self._neutralize(node, session, instrument)
        if name in {"delay", "delta"}:
            window = _window(node.children[1])
            if session < window:
                return missing(Alpha101Reason.WINDOW_INCOMPLETE)
            prior = self._cell(node.children[0], session - window, instrument)
            if name == "delay":
                return prior
            current = self._cell(node.children[0], session, instrument)
            return _subtract(current, prior)
        if name in _ROLLING or (name in {"min", "max"} and node.children[1].kind == "number"):
            return self._rolling(node, session, instrument)
        cells = tuple(self._cell(child, session, instrument) for child in node.children)
        if any(cell.reason is not None for cell in cells):
            return _preferred_failure(*cells)
        values = tuple(cell.value for cell in cells)
        if any(value is None for value in values):
            return missing(Alpha101Reason.INPUT_MISSING)
        clean = tuple(float(value) for value in values if value is not None)
        functions: dict[str, Callable[[tuple[float, ...]], float]] = {
            "abs": lambda args: abs(args[0]),
            "sign": lambda args: float((args[0] > 0) - (args[0] < 0)),
            "log": lambda args: logarithm(args[0]),
            "signedpower": lambda args: signed_power(args[0], args[1]),
            "min": lambda args: min(args),
            "max": lambda args: max(args),
        }
        return self._attempt(lambda: functions[name](clean))

    def _cross(self, node: AstNode, session: int, instrument: int) -> Alpha101Cell:
        target = self._cell(node.children[0], session, instrument)
        if target.reason is not None:
            return target
        members = self.panel.members(session)
        cells = tuple(
            self._cell(node.children[0], session, index)
            for index, member in enumerate(members)
            if member
        )
        observed = tuple(
            cell.value for cell in cells if cell.reason is None and cell.value is not None
        )
        try:
            transformed = (
                average_rank(observed)
                if node.value == "rank"
                else scale(
                    observed,
                    float(node.children[1].value) if len(node.children) == 2 else 1,
                )
            )
        except Alpha101Failure as failure:
            return missing(failure.reason)
        target_position = [
            index
            for index, member in enumerate(members)
            if member
            and self._cell(node.children[0], session, index).reason is None
            and self._cell(node.children[0], session, index).value is not None
        ].index(instrument)
        return Alpha101Cell(transformed[target_position])

    def _neutralize(self, node: AstNode, session: int, instrument: int) -> Alpha101Cell:
        members = self.panel.members(session)
        if not members[instrument]:
            return missing(Alpha101Reason.INPUT_MISSING)
        level = node.children[1].value.removeprefix("indclass.")
        groups = self.panel.industry_groups(session, level)
        group = groups[instrument]
        if group is None:
            return missing(
                {
                    "sector": Alpha101Reason.SW_L1_NOT_POINT_IN_TIME,
                    "industry": Alpha101Reason.SW_L2_NOT_POINT_IN_TIME,
                    "subindustry": Alpha101Reason.SW_L3_UNAVAILABLE,
                }[level]
            )
        positions = [
            index for index, value in enumerate(groups) if members[index] and value == group
        ]
        cells = tuple(self._cell(node.children[0], session, index) for index in positions)
        target = cells[positions.index(instrument)]
        if target.reason is not None:
            return target
        observed = tuple(
            cell.value for cell in cells if cell.reason is None and cell.value is not None
        )
        return self._attempt(
            lambda: finite((target.value or 0) - finite(sum(observed) / len(observed)))
        )

    def _rolling(self, node: AstNode, session: int, instrument: int) -> Alpha101Cell:
        window = _window(node.children[-1])
        if session + 1 < window:
            current = tuple(
                self._cell(source, session, instrument) for source in node.children[:-1]
            )
            not_applicable = tuple(cell for cell in current if cell.reason in _N_A_REASONS)
            if not_applicable:
                return _preferred_failure(*not_applicable)
            return missing(Alpha101Reason.WINDOW_INCOMPLETE)
        source_nodes = node.children[:-1]
        series = tuple(
            tuple(
                self._cell(source, day, instrument)
                for day in range(session - window + 1, session + 1)
            )
            for source in source_nodes
        )
        cells = tuple(cell for values in series for cell in values)
        if any(cell.reason is not None for cell in cells):
            return _preferred_failure(*cells)
        values = tuple(
            tuple(float(cell.value) for cell in cells_by_source if cell.value is not None)
            for cells_by_source in series
        )
        rolling_name = f"ts_{node.value}" if node.value in {"min", "max"} else node.value
        functions = {
            "sum": lambda: finite(sum(values[0])),
            "product": lambda: finite(prod(values[0])),
            "stddev": lambda: stddev(values[0]),
            "ts_min": lambda: min(values[0]),
            "ts_max": lambda: max(values[0]),
            "ts_rank": lambda: time_series_rank(values[0]),
            "ts_argmax": lambda: first_extreme_position(values[0], maximum=True),
            "ts_argmin": lambda: first_extreme_position(values[0], maximum=False),
            "decay_linear": lambda: decay_linear(values[0]),
            "correlation": lambda: correlation(values[0], values[1]),
            "covariance": lambda: covariance(values[0], values[1]),
        }
        return self._attempt(functions[rolling_name])

    @staticmethod
    def _apply(
        function: Callable[[float], float],
        cell: Alpha101Cell,
    ) -> Alpha101Cell:
        if cell.reason is not None or cell.value is None:
            return cell
        value = cell.value
        return ScalarReferenceEvaluator._attempt(lambda: function(value))

    @staticmethod
    def _attempt(function: Callable[[], float]) -> Alpha101Cell:
        try:
            return Alpha101Cell(finite(function()))
        except Alpha101Failure as failure:
            return missing(failure.reason)


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


def _window(node: AstNode) -> int:
    return floor(float(node.value))


def _subtract(left: Alpha101Cell, right: Alpha101Cell) -> Alpha101Cell:
    if left.reason is not None or right.reason is not None:
        return _preferred_failure(left, right)
    if left.value is None or right.value is None:
        return missing(Alpha101Reason.INPUT_MISSING)
    return Alpha101Cell(finite(left.value - right.value))


def _preferred_failure(*cells: Alpha101Cell) -> Alpha101Cell:
    reasons = tuple(cell.reason for cell in cells if cell.reason is not None)
    for reason in reasons:
        if reason in _N_A_REASONS:
            return missing(reason)
    return missing(reasons[0] if reasons else Alpha101Reason.INPUT_MISSING)


__all__ = [
    "SCALAR_REFERENCE_GENERATOR_VERSION",
    "ScalarReferenceEvaluator",
    "scalar_reference_source_hash",
]
