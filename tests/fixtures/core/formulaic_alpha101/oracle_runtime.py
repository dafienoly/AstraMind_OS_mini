"""Stdlib-only values, parser and scalar math for the frozen Alpha101 oracle."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

OBSERVED = "observed"
MISSING = "missing"
NOT_APPLICABLE = "not_applicable"

INPUT_MISSING = "alpha101_input_missing"
WINDOW_INCOMPLETE = "alpha101_window_incomplete"
NO_LEGAL_BAR = "alpha101_no_legal_bar"
ZERO_DENOMINATOR = "alpha101_zero_denominator"
ZERO_VARIANCE = "alpha101_zero_variance"
LOG_DOMAIN = "alpha101_log_domain"
POWER_DOMAIN = "alpha101_power_domain"
SCALE_ZERO_NORM = "alpha101_scale_zero_norm"
CROSS_SECTION_TOO_SMALL = "alpha101_cross_section_too_small"
NONFINITE = "alpha101_nonfinite"
SW_L1_NOT_POINT_IN_TIME = "alpha101_sw_l1_not_point_in_time"
SW_L2_NOT_POINT_IN_TIME = "alpha101_sw_l2_not_point_in_time"
SW_L3_UNAVAILABLE = "alpha101_sw_l3_unavailable"

NOT_APPLICABLE_REASONS = {
    SW_L1_NOT_POINT_IN_TIME,
    SW_L2_NOT_POINT_IN_TIME,
    SW_L3_UNAVAILABLE,
}


class OracleFailure(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Cell:
    value: float | None
    reason: str | None = None

    @property
    def state(self) -> str:
        if self.reason is None:
            return OBSERVED
        return NOT_APPLICABLE if self.reason in NOT_APPLICABLE_REASONS else MISSING

    def frozen(self) -> list[str | None]:
        value = self.value.hex() if self.value is not None else None
        return [self.state, self.reason, value]


def observed(value: float) -> Cell:
    return Cell(finite(value))


def unavailable(reason: str) -> Cell:
    return Cell(None, reason)


def finite(value: float) -> float:
    if not math.isfinite(value):
        raise OracleFailure(NONFINITE)
    return value


def divide(numerator: float, denominator: float) -> float:
    finite(numerator)
    finite(denominator)
    if denominator == 0:
        raise OracleFailure(ZERO_DENOMINATOR)
    return finite(numerator / denominator)


def logarithm(value: float) -> float:
    if value <= 0:
        raise OracleFailure(LOG_DOMAIN)
    return finite(math.log(value))


def power(base: float, exponent: float) -> float:
    if (base == 0 and exponent <= 0) or (base < 0 and not exponent.is_integer()):
        raise OracleFailure(POWER_DOMAIN)
    try:
        return finite(base**exponent)
    except OverflowError as error:
        raise OracleFailure(NONFINITE) from error


def signed_power(base: float, exponent: float) -> float:
    if base == 0 and exponent <= 0:
        raise OracleFailure(POWER_DOMAIN)
    try:
        return finite(math.copysign(abs(base) ** exponent, base) if base else 0.0)
    except OverflowError as error:
        raise OracleFailure(NONFINITE) from error


def average_rank(values: Sequence[float]) -> tuple[float, ...]:
    if len(values) < 2:
        raise OracleFailure(CROSS_SECTION_TOO_SMALL)
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = ((start + end - 1) / 2) / (len(values) - 1)
        for position in order[start:end]:
            result[position] = rank
        start = end
    return tuple(result)


def scale(values: Sequence[float], target: float = 1.0) -> tuple[float, ...]:
    norm = finite(sum(abs(value) for value in values))
    if norm == 0:
        raise OracleFailure(SCALE_ZERO_NORM)
    return tuple(finite(value * target / norm) for value in values)


def stddev(values: Sequence[float]) -> float:
    try:
        mean = finite(sum(values) / len(values))
        deviations = finite(sum((value - mean) ** 2 for value in values))
        return finite(math.sqrt(deviations / len(values)))
    except OverflowError as error:
        raise OracleFailure(NONFINITE) from error


def covariance(left: Sequence[float], right: Sequence[float]) -> float:
    try:
        left_mean = finite(sum(left) / len(left))
        right_mean = finite(sum(right) / len(right))
        products = finite(
            sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
        )
        return finite(products / len(left))
    except OverflowError as error:
        raise OracleFailure(NONFINITE) from error


def correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) == len(right) == 2:
        left_delta = finite(left[1] - left[0])
        right_delta = finite(right[1] - right[0])
        if left_delta == 0 or right_delta == 0:
            raise OracleFailure(ZERO_VARIANCE)
        return 1.0 if (left_delta > 0) == (right_delta > 0) else -1.0
    left_std = stddev(left)
    right_std = stddev(right)
    if left_std == 0 or right_std == 0:
        raise OracleFailure(ZERO_VARIANCE)
    return divide(covariance(left, right), left_std * right_std)


def decay_linear(values: Sequence[float]) -> float:
    weights = range(1, len(values) + 1)
    return finite(
        sum(value * weight for value, weight in zip(values, weights, strict=True)) / sum(weights)
    )


def first_extreme_position(values: Sequence[float], *, maximum: bool) -> float:
    extreme = max(values) if maximum else min(values)
    return float(values.index(extreme))


@dataclass(frozen=True)
class Node:
    kind: str
    value: str
    children: tuple[Node, ...] = ()


_LEXEME_PATTERN = re.compile(
    r"\s*(?:(?P<number>(?:\d+(?:\.\d*)?|\.\d+))|"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_.]*)|(?P<op>\|\||==|[()+\-*/^,<>=?:]))"
)


class Parser:
    def __init__(self, source: str) -> None:
        self.tokens = self._tokenize(source)
        self.position = 0

    @staticmethod
    def _tokenize(source: str) -> tuple[tuple[str, str], ...]:
        result = []
        position = 0
        while position < len(source):
            match = _LEXEME_PATTERN.match(source, position)
            if match is None or match.lastgroup is None:
                raise ValueError(f"oracle parser rejected token at {position}")
            result.append((match.lastgroup, match.group(match.lastgroup)))
            position = match.end()
        return tuple(result)

    def parse(self) -> Node:
        node = self._conditional()
        if self.position != len(self.tokens):
            raise ValueError("oracle parser found trailing input")
        return node

    def _conditional(self) -> Node:
        condition = self._logical_or()
        if not self._accept("?"):
            return condition
        when_true = self._conditional()
        self._expect(":")
        return Node("ternary", "?:", (condition, when_true, self._conditional()))

    def _logical_or(self) -> Node:
        left = self._comparison()
        while self._accept("||"):
            left = Node("binary", "||", (left, self._comparison()))
        return left

    def _comparison(self) -> Node:
        left = self._additive()
        while self._peek_text() in {"==", "<", ">"}:
            operator = self._take()[1]
            left = Node("binary", operator, (left, self._additive()))
        return left

    def _additive(self) -> Node:
        left = self._multiplicative()
        while self._peek_text() in {"+", "-"}:
            operator = self._take()[1]
            left = Node("binary", operator, (left, self._multiplicative()))
        return left

    def _multiplicative(self) -> Node:
        left = self._unary()
        while self._peek_text() in {"*", "/"}:
            operator = self._take()[1]
            left = Node("binary", operator, (left, self._unary()))
        return left

    def _unary(self) -> Node:
        text = self._peek_text()
        if text in {"+", "-"}:
            self.position += 1
            return Node("unary", text, (self._unary(),))
        return self._power()

    def _power(self) -> Node:
        left = self._primary()
        if self._accept("^"):
            return Node("binary", "^", (left, self._unary()))
        return left

    def _primary(self) -> Node:
        kind, text = self._take()
        if text == "(":
            node = self._conditional()
            self._expect(")")
            return node
        if kind == "number":
            return Node("number", text)
        if kind != "name":
            raise ValueError(f"oracle parser rejected prefix {text}")
        if self._peek_text() != "(":
            return Node("identifier", text.lower())
        self.position += 1
        children = []
        if self._peek_text() != ")":
            while True:
                children.append(self._conditional())
                if not self._accept(","):
                    break
        self._expect(")")
        return Node("call", text.lower(), tuple(children))

    def _peek_text(self) -> str | None:
        return self.tokens[self.position][1] if self.position < len(self.tokens) else None

    def _accept(self, expected: str) -> bool:
        if self._peek_text() != expected:
            return False
        self.position += 1
        return True

    def _take(self) -> tuple[str, str]:
        if self.position >= len(self.tokens):
            raise ValueError("oracle parser reached unexpected end")
        item = self.tokens[self.position]
        self.position += 1
        return item

    def _expect(self, expected: str) -> None:
        _kind, actual = self._take()
        if actual != expected:
            raise ValueError(f"oracle parser expected {expected}, received {actual}")


def preferred_failure(*cells: Cell) -> Cell:
    reasons = tuple(cell.reason for cell in cells if cell.reason is not None)
    for reason in reasons:
        if reason in NOT_APPLICABLE_REASONS:
            return unavailable(reason)
    return unavailable(reasons[0] if reasons else INPUT_MISSING)
