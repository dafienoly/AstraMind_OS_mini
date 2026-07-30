"""Matrix operations for the production Alpha101 AST evaluator."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import cast

from .inputs import Alpha101Panel
from .reasons import Alpha101Failure, Alpha101Reason
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
from .values import Alpha101Cell, Matrix, missing

_N_A_REASONS = {
    Alpha101Reason.SW_L1_NOT_POINT_IN_TIME,
    Alpha101Reason.SW_L2_NOT_POINT_IN_TIME,
    Alpha101Reason.SW_L3_UNAVAILABLE,
}


def constant(panel: Alpha101Panel, value: float) -> Matrix:
    return tuple(tuple(Alpha101Cell(value) for _ in panel.instruments) for _ in panel.sessions)


def unary(matrix: Matrix, operator: str) -> Matrix:
    if operator == "+":
        return matrix
    if operator == "-":
        return _map_cells(matrix, lambda value: finite(-value))
    raise ValueError(f"unsupported unary operator {operator}")


def binary(left: Matrix, right: Matrix, operator: str) -> Matrix:
    if operator == "||":
        return _logical_or(left, right)

    def apply(x: float, y: float) -> float:
        if operator == "+":
            return finite(x + y)
        if operator == "-":
            return finite(x - y)
        if operator == "*":
            return finite(x * y)
        if operator == "/":
            return divide(x, y)
        if operator == "^":
            return power(x, y)
        if operator == "<":
            return float(x < y)
        if operator == ">":
            return float(x > y)
        if operator == "==":
            return float(x == y)
        raise ValueError(f"unsupported binary operator {operator}")

    return _zip_cells(left, right, apply)


def ternary(condition: Matrix, when_true: Matrix, when_false: Matrix) -> Matrix:
    rows = []
    for condition_row, true_row, false_row in zip(
        condition,
        when_true,
        when_false,
        strict=True,
    ):
        rows.append(
            tuple(
                missing(test.reason)
                if test.reason is not None
                else (yes if test.value != 0 else no)
                for test, yes, no in zip(condition_row, true_row, false_row, strict=True)
            )
        )
    return tuple(rows)


def elementwise_call(name: str, arguments: tuple[Matrix, ...]) -> Matrix:
    if name == "abs":
        return _map_cells(arguments[0], abs)
    if name == "sign":
        return _map_cells(arguments[0], lambda value: float((value > 0) - (value < 0)))
    if name == "log":
        return _map_cells(arguments[0], logarithm)
    if name == "signedpower":
        return _zip_cells(arguments[0], arguments[1], signed_power)
    if name in {"min", "max"}:
        function = min if name == "min" else max
        return _zip_cells(arguments[0], arguments[1], function)
    raise ValueError(f"unsupported elementwise function {name}")


def cross_section(matrix: Matrix, panel: Alpha101Panel, name: str, target: float = 1.0) -> Matrix:
    result = []
    for session_index, row in enumerate(matrix):
        members = panel.members(session_index)
        positions = [
            index
            for index, cell in enumerate(row)
            if members[index] and cell.reason is None and cell.value is not None
        ]
        values = [cast(float, row[index].value) for index in positions]
        failure_reason: Alpha101Reason | None
        try:
            transformed = average_rank(values) if name == "rank" else scale(values, target)
        except Alpha101Failure as failure:
            transformed = ()
            failure_reason = failure.reason
        else:
            failure_reason = None
        output = list(row)
        for index, member in enumerate(members):
            if not member and output[index].reason is None:
                output[index] = missing(Alpha101Reason.INPUT_MISSING)
        for offset, position in enumerate(positions):
            output[position] = (
                Alpha101Cell(transformed[offset])
                if failure_reason is None
                else missing(failure_reason)
            )
        result.append(tuple(output))
    return tuple(result)


def indneutralize(matrix: Matrix, panel: Alpha101Panel, level: str) -> Matrix:
    reason = {
        "sector": Alpha101Reason.SW_L1_NOT_POINT_IN_TIME,
        "industry": Alpha101Reason.SW_L2_NOT_POINT_IN_TIME,
        "subindustry": Alpha101Reason.SW_L3_UNAVAILABLE,
    }[level]
    result = []
    for session_index, row in enumerate(matrix):
        groups = panel.industry_groups(session_index, level)
        members = panel.members(session_index)
        grouped: dict[str, list[int]] = {}
        output = list(row)
        for position, (cell, group, member) in enumerate(zip(row, groups, members, strict=True)):
            if not member:
                output[position] = missing(Alpha101Reason.INPUT_MISSING)
            elif group is None:
                output[position] = missing(reason)
            elif cell.reason is None:
                grouped.setdefault(group, []).append(position)
        for positions in grouped.values():
            try:
                mean = finite(
                    sum(row[position].value or 0 for position in positions) / len(positions)
                )
                for position in positions:
                    output[position] = Alpha101Cell(finite((row[position].value or 0) - mean))
            except Alpha101Failure as failure:
                for position in positions:
                    output[position] = missing(failure.reason)
        result.append(tuple(output))
    return tuple(result)


def delay(matrix: Matrix, window: int) -> Matrix:
    width = len(matrix[0])
    unavailable = tuple(missing(Alpha101Reason.WINDOW_INCOMPLETE) for _ in range(width))
    return tuple(
        unavailable if index < window else matrix[index - window] for index in range(len(matrix))
    )


def rolling(
    matrices: tuple[Matrix, ...],
    window: int,
    function: Callable[[tuple[tuple[float, ...], ...]], float],
) -> Matrix:
    result = []
    width = len(matrices[0][0])
    for session_index in range(len(matrices[0])):
        row = []
        for instrument_index in range(width):
            if session_index + 1 < window:
                current_reasons = tuple(
                    matrix[session_index][instrument_index].reason for matrix in matrices
                )
                not_applicable = next(
                    (
                        reason
                        for reason in current_reasons
                        if reason is not None and reason in _N_A_REASONS
                    ),
                    None,
                )
                row.append(missing(not_applicable or Alpha101Reason.WINDOW_INCOMPLETE))
                continue
            series = tuple(
                tuple(
                    matrix[day_index][instrument_index].value
                    for day_index in range(session_index - window + 1, session_index + 1)
                )
                for matrix in matrices
            )
            reasons = tuple(
                cast(Alpha101Reason, matrix[day_index][instrument_index].reason)
                for matrix in matrices
                for day_index in range(session_index - window + 1, session_index + 1)
                if matrix[day_index][instrument_index].reason is not None
            )
            if reasons or any(value is None for values in series for value in values):
                row.append(missing(_preferred_reason(reasons) or Alpha101Reason.INPUT_MISSING))
                continue
            try:
                clean = tuple(
                    tuple(value for value in values if value is not None) for values in series
                )
                row.append(Alpha101Cell(finite(function(clean))))
            except Alpha101Failure as failure:
                row.append(missing(failure.reason))
        result.append(tuple(row))
    return tuple(result)


def _map_cells(matrix: Matrix, function: Callable[[float], float]) -> Matrix:
    result = []
    for row in matrix:
        output = []
        for cell in row:
            if cell.reason is not None or cell.value is None:
                output.append(cell)
                continue
            try:
                output.append(Alpha101Cell(finite(function(cell.value))))
            except Alpha101Failure as failure:
                output.append(missing(failure.reason))
        result.append(tuple(output))
    return tuple(result)


def _zip_cells(
    left: Matrix,
    right: Matrix,
    function: Callable[[float, float], float],
) -> Matrix:
    result = []
    for left_row, right_row in zip(left, right, strict=True):
        output = []
        for left_cell, right_cell in zip(left_row, right_row, strict=True):
            reason = _preferred_reason(
                tuple(item for item in (left_cell.reason, right_cell.reason) if item is not None)
            )
            if reason is not None or left_cell.value is None or right_cell.value is None:
                output.append(missing(reason or Alpha101Reason.INPUT_MISSING))
                continue
            try:
                output.append(Alpha101Cell(finite(function(left_cell.value, right_cell.value))))
            except Alpha101Failure as failure:
                output.append(missing(failure.reason))
        result.append(tuple(output))
    return tuple(result)


def _preferred_reason(reasons: tuple[Alpha101Reason, ...]) -> Alpha101Reason | None:
    for reason in reasons:
        if reason in _N_A_REASONS:
            return reason
    return reasons[0] if reasons else None


def _logical_or(left: Matrix, right: Matrix) -> Matrix:
    result = []
    for left_row, right_row in zip(left, right, strict=True):
        output = []
        for left_cell, right_cell in zip(left_row, right_row, strict=True):
            if left_cell.reason is None and left_cell.value != 0:
                output.append(Alpha101Cell(1.0))
            elif left_cell.reason is None:
                output.append(
                    right_cell
                    if right_cell.reason is not None
                    else Alpha101Cell(float(right_cell.value != 0))
                )
            elif right_cell.reason is None and right_cell.value != 0:
                output.append(Alpha101Cell(1.0))
            else:
                reason = _preferred_reason(
                    tuple(
                        item for item in (left_cell.reason, right_cell.reason) if item is not None
                    )
                )
                output.append(missing(reason or Alpha101Reason.INPUT_MISSING))
        result.append(tuple(output))
    return tuple(result)


def rolling_function(name: str) -> Callable[[tuple[tuple[float, ...], ...]], float]:
    functions: dict[str, Callable[[tuple[tuple[float, ...], ...]], float]] = {
        "sum": lambda values: finite(sum(values[0])),
        "product": lambda values: finite(math.prod(values[0])),
        "stddev": lambda values: stddev(values[0]),
        "ts_min": lambda values: min(values[0]),
        "ts_max": lambda values: max(values[0]),
        "ts_rank": lambda values: time_series_rank(values[0]),
        "ts_argmax": lambda values: first_extreme_position(values[0], maximum=True),
        "ts_argmin": lambda values: first_extreme_position(values[0], maximum=False),
        "decay_linear": lambda values: decay_linear(values[0]),
        "correlation": lambda values: correlation(values[0], values[1]),
        "covariance": lambda values: covariance(values[0], values[1]),
    }
    return functions[name]


__all__ = [
    "binary",
    "constant",
    "cross_section",
    "delay",
    "elementwise_call",
    "indneutralize",
    "rolling",
    "rolling_function",
    "ternary",
    "unary",
]
