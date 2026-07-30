"""Cell-at-a-time Alpha101 oracle independent of production implementation."""

from __future__ import annotations

from collections.abc import Callable
from math import floor, prod
from typing import cast

from .oracle_panel import OraclePanel
from .oracle_runtime import (
    INPUT_MISSING,
    NOT_APPLICABLE_REASONS,
    WINDOW_INCOMPLETE,
    Cell,
    Node,
    OracleFailure,
    Parser,
    average_rank,
    correlation,
    covariance,
    decay_linear,
    divide,
    finite,
    first_extreme_position,
    logarithm,
    observed,
    power,
    preferred_failure,
    scale,
    signed_power,
    stddev,
    unavailable,
)

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


class OracleEvaluator:
    def __init__(self, panel: OraclePanel) -> None:
        self.panel = panel
        self._cache: dict[tuple[Node, int, int], Cell] = {}
        self._inputs: dict[str, tuple[tuple[Cell, ...], ...]] = {}

    def evaluate(self, formula: str, *, session: int, instrument: int) -> Cell:
        return self._cell(Parser(formula).parse(), session, instrument)

    def _cell(self, node: Node, session: int, instrument: int) -> Cell:
        key = node, session, instrument
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        result = self._uncached(node, session, instrument)
        self._cache[key] = result
        return result

    def _uncached(self, node: Node, session: int, instrument: int) -> Cell:
        if node.kind == "number":
            return observed(float(node.value))
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
        raise ValueError(f"unsupported oracle AST kind {node.kind}")

    def _binary(self, node: Node, session: int, instrument: int) -> Cell:
        left = self._cell(node.children[0], session, instrument)
        if node.value == "||" and left.reason is None and left.value != 0:
            return observed(1.0)
        right = self._cell(node.children[1], session, instrument)
        if node.value == "||":
            if left.reason is None:
                return right if right.reason is not None else observed(float(right.value != 0))
            if right.reason is None and right.value != 0:
                return observed(1.0)
            return preferred_failure(left, right)
        if left.reason is not None or right.reason is not None:
            return preferred_failure(left, right)
        if left.value is None or right.value is None:
            return unavailable(INPUT_MISSING)
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

    def _call(self, node: Node, session: int, instrument: int) -> Cell:
        name = node.value
        if name in {"rank", "scale"}:
            return self._cross(node, session, instrument)
        if name == "indneutralize":
            return self._neutralize(node, session, instrument)
        if name in {"delay", "delta"}:
            window = _window(node.children[1])
            if session < window:
                return unavailable(WINDOW_INCOMPLETE)
            delayed = self._cell(node.children[0], session - window, instrument)
            if name == "delay":
                return delayed
            return _subtract(self._cell(node.children[0], session, instrument), delayed)
        if name in _ROLLING or (name in {"min", "max"} and node.children[1].kind == "number"):
            return self._rolling(node, session, instrument)
        cells = tuple(self._cell(child, session, instrument) for child in node.children)
        if any(cell.reason is not None for cell in cells):
            return preferred_failure(*cells)
        values = tuple(cell.value for cell in cells)
        if any(value is None for value in values):
            return unavailable(INPUT_MISSING)
        clean = tuple(float(value) for value in values if value is not None)
        functions: dict[str, Callable[[tuple[float, ...]], float]] = {
            "abs": lambda args: abs(args[0]),
            "sign": lambda args: float((args[0] > 0) - (args[0] < 0)),
            "log": lambda args: logarithm(args[0]),
            "signedpower": lambda args: signed_power(args[0], args[1]),
            "min": min,
            "max": max,
        }
        return self._attempt(lambda: functions[name](clean))

    def _cross(self, node: Node, session: int, instrument: int) -> Cell:
        target = self._cell(node.children[0], session, instrument)
        if target.reason is not None:
            return target
        members = self.panel.members(session)
        positions = [
            index
            for index, member in enumerate(members)
            if member
            and self._cell(node.children[0], session, index).reason is None
            and self._cell(node.children[0], session, index).value is not None
        ]
        if instrument not in positions:
            return unavailable(INPUT_MISSING)
        values = tuple(
            cast(float, self._cell(node.children[0], session, index).value)
            for index in positions
            if self._cell(node.children[0], session, index).value is not None
        )
        try:
            transformed = (
                average_rank(values)
                if node.value == "rank"
                else scale(
                    values,
                    float(node.children[1].value) if len(node.children) == 2 else 1.0,
                )
            )
        except OracleFailure as failure:
            return unavailable(failure.reason)
        return observed(transformed[positions.index(instrument)])

    def _neutralize(self, node: Node, session: int, instrument: int) -> Cell:
        members = self.panel.members(session)
        if not members[instrument]:
            return unavailable(INPUT_MISSING)
        level = node.children[1].value.removeprefix("indclass.")
        groups = self.panel.industry_groups(session, level)
        group = groups[instrument]
        if group is None:
            return unavailable(self.panel.unavailable_industry_reason(level))
        positions = [
            index for index, value in enumerate(groups) if members[index] and value == group
        ]
        cells = tuple(self._cell(node.children[0], session, index) for index in positions)
        target = cells[positions.index(instrument)]
        if target.reason is not None:
            return target
        observed_values = tuple(
            float(cell.value) for cell in cells if cell.reason is None and cell.value is not None
        )
        return self._attempt(
            lambda: finite(
                cast(float, target.value) - finite(sum(observed_values) / len(observed_values))
            )
        )

    def _rolling(self, node: Node, session: int, instrument: int) -> Cell:
        window = _window(node.children[-1])
        sources = node.children[:-1]
        if session + 1 < window:
            current = tuple(self._cell(source, session, instrument) for source in sources)
            not_applicable = tuple(
                cell for cell in current if cell.reason in NOT_APPLICABLE_REASONS
            )
            return (
                preferred_failure(*not_applicable)
                if not_applicable
                else unavailable(WINDOW_INCOMPLETE)
            )
        series = tuple(
            tuple(
                self._cell(source, day, instrument)
                for day in range(session - window + 1, session + 1)
            )
            for source in sources
        )
        cells = tuple(cell for values in series for cell in values)
        if any(cell.reason is not None for cell in cells):
            return preferred_failure(*cells)
        values = tuple(
            tuple(float(cell.value) for cell in cells_by_source if cell.value is not None)
            for cells_by_source in series
        )
        name = f"ts_{node.value}" if node.value in {"min", "max"} else node.value
        functions: dict[str, Callable[[], float]] = {
            "sum": lambda: finite(sum(values[0])),
            "product": lambda: finite(prod(values[0])),
            "stddev": lambda: stddev(values[0]),
            "ts_min": lambda: min(values[0]),
            "ts_max": lambda: max(values[0]),
            "ts_rank": lambda: average_rank(values[0])[-1],
            "ts_argmax": lambda: first_extreme_position(values[0], maximum=True),
            "ts_argmin": lambda: first_extreme_position(values[0], maximum=False),
            "decay_linear": lambda: decay_linear(values[0]),
            "correlation": lambda: correlation(values[0], values[1]),
            "covariance": lambda: covariance(values[0], values[1]),
        }
        return self._attempt(functions[name])

    @staticmethod
    def _apply(function: Callable[[float], float], cell: Cell) -> Cell:
        if cell.reason is not None or cell.value is None:
            return cell
        return OracleEvaluator._attempt(lambda: function(cast(float, cell.value)))

    @staticmethod
    def _attempt(function: Callable[[], float]) -> Cell:
        try:
            return observed(function())
        except (OracleFailure, OverflowError) as failure:
            reason = failure.reason if isinstance(failure, OracleFailure) else "alpha101_nonfinite"
            return unavailable(reason)


def _window(node: Node) -> int:
    return floor(float(node.value))


def _subtract(left: Cell, right: Cell) -> Cell:
    if left.reason is not None or right.reason is not None:
        return preferred_failure(left, right)
    if left.value is None or right.value is None:
        return unavailable(INPUT_MISSING)
    left_value = left.value
    right_value = right.value
    return observed(finite(left_value - right_value))
