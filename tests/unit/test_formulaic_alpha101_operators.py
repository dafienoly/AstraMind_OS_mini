import hashlib
import json
import math
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from astramind_mini.strategy_research.core.formulaic_alpha101 import evaluator as evaluator_module
from astramind_mini.strategy_research.core.formulaic_alpha101.evaluator import Alpha101Evaluator
from astramind_mini.strategy_research.core.formulaic_alpha101.inputs import (
    Alpha101DailyObservation,
    Alpha101Panel,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.operations import (
    binary,
    rolling,
    ternary,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.reasons import (
    Alpha101Failure,
    Alpha101Reason,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.registry import (
    ALPHA101_DEFINITIONS,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.scalar_operators import (
    average_rank,
    correlation,
    covariance,
    decay_linear,
    divide,
    first_extreme_position,
    logarithm,
    power,
    scale,
    signed_power,
    stddev,
    time_series_rank,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.syntax import (
    AstNode,
    decimal_tokens,
    parse_formula,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.values import (
    Alpha101Cell,
    Matrix,
    missing,
)
from tests.fixtures.core.formulaic_alpha101.factory import full_panel
from tests.fixtures.core.formulaic_alpha101.independent_oracle import (
    generator_source_hash,
    independent_operator_expected,
)
from tests.fixtures.core.formulaic_alpha101.oracle_evaluator import OracleEvaluator
from tests.fixtures.core.formulaic_alpha101.oracle_panel import OraclePanel
from tests.fixtures.core.formulaic_alpha101.oracle_runtime import Parser


def assert_failure(reason: Alpha101Reason, function: Callable[[], object]) -> None:
    with pytest.raises(Alpha101Failure) as captured:
        function()
    assert captured.value.reason == reason


def test_rank_ties_percentiles_and_small_cross_section() -> None:
    assert average_rank((10.0, 20.0, 20.0, 40.0)) == (0.0, 0.5, 0.5, 1.0)
    assert time_series_rank((4.0, 2.0, 2.0)) == 0.25
    assert_failure(Alpha101Reason.CROSS_SECTION_TOO_SMALL, lambda: average_rank((1.0,)))


def test_population_statistics_extremes_and_decay_are_hand_reproducible() -> None:
    assert stddev((1.0, 2.0, 3.0)) == pytest.approx(math.sqrt(2 / 3), abs=1e-12)
    assert covariance((1.0, 2.0, 3.0), (2.0, 4.0, 8.0)) == pytest.approx(2.0, abs=1e-12)
    assert correlation((1.0, 2.0, 3.0), (2.0, 4.0, 6.0)) == pytest.approx(1.0, abs=1e-12)
    assert decay_linear((10.0, 20.0, 40.0)) == pytest.approx(170 / 6, abs=1e-12)
    assert first_extreme_position((3.0, 7.0, 7.0), maximum=True) == 1.0
    assert first_extreme_position((2.0, 1.0, 1.0), maximum=False) == 1.0
    assert_failure(
        Alpha101Reason.ZERO_VARIANCE,
        lambda: correlation((1.0, 1.0), (2.0, 3.0)),
    )
    assert correlation((1.0, 3.0), (4.0, 9.0)) == 1.0
    assert correlation((1.0, 3.0), (9.0, 4.0)) == -1.0


def test_signedpower_is_sign_preserving_and_never_simplified_to_power() -> None:
    assert signed_power(-2.0, 2.0) == -4.0
    assert power(-2.0, 2.0) == 4.0
    assert signed_power(-4.0, 0.5) == -2.0
    assert_failure(Alpha101Reason.POWER_DOMAIN, lambda: power(-4.0, 0.5))


def test_domains_zero_norm_and_nonfinite_fail_closed() -> None:
    assert_failure(Alpha101Reason.ZERO_DENOMINATOR, lambda: divide(1.0, 0.0))
    assert_failure(Alpha101Reason.LOG_DOMAIN, lambda: logarithm(0.0))
    assert_failure(Alpha101Reason.POWER_DOMAIN, lambda: power(0.0, 0.0))
    assert_failure(Alpha101Reason.SCALE_ZERO_NORM, lambda: scale((0.0, 0.0)))
    assert_failure(Alpha101Reason.NONFINITE, lambda: power(10.0, 1000.0))
    assert_failure(Alpha101Reason.NONFINITE, lambda: divide(1.0, float("inf")))
    assert_failure(
        Alpha101Reason.NONFINITE,
        lambda: scale((1e308, 1e308)),
    )
    with pytest.raises(ValueError, match="finite"):
        Alpha101Cell(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        Alpha101Cell(float("inf"))
    with pytest.raises(ValueError, match="reason"):
        Alpha101Cell(1.0, Alpha101Reason.INPUT_MISSING)
    with pytest.raises(ValueError, match="finite"):
        Alpha101Cell(None)
    boundary = json.loads(
        Path("tests/fixtures/core/formulaic_alpha101/golden_edge_65d.json").read_text()
    )["input_boundary_expectations"]
    assert boundary == {
        "finite": "accepted",
        "nan": "rejected",
        "positive_inf": "rejected",
        "negative_inf": "rejected",
    }
    for value in (float("nan"), float("inf"), float("-inf")):
        observation = full_panel().observations[0].model_dump()
        observation["raw_volume_shares"] = value
        with pytest.raises(ValidationError, match=r"finite|raw_volume_shares"):
            Alpha101DailyObservation.model_validate(observation)


def test_parser_preserves_decimal_tokens_and_min_max_overload_shape() -> None:
    formula = "min(rank(close), 7.89291) + max(open, close)"
    node = parse_formula(formula)
    assert decimal_tokens(formula) == ("7.89291",)
    assert node.children[0].kind == "call"
    assert node.children[0].children[1].kind == "number"
    assert node.children[1].children[1].kind == "identifier"


@pytest.mark.parametrize(
    ("expression", "expected", "expected_root"),
    (
        ("-2^2", -4.0, ("unary", "-")),
        ("(-2)^2", 4.0, ("binary", "^")),
        ("2^-2", 0.25, ("binary", "^")),
        ("--2", 2.0, ("unary", "-")),
        ("2^3^2", 512.0, ("binary", "^")),
        ("-2^2 < -3 ? 7^2 : 2^-2", 49.0, ("ternary", "?:")),
    ),
)
def test_unary_power_comparison_and_conditional_precedence_has_two_executed_paths(
    expression: str,
    expected: float,
    expected_root: tuple[str, str],
) -> None:
    panel = full_panel(session_count=5)
    production_node = parse_formula(expression)
    independent_node = Parser(expression).parse()
    production_cell = Alpha101Evaluator(panel)._node(production_node)[-1][0]
    independent_cell = OracleEvaluator(OraclePanel("edge_65d")).evaluate(
        expression,
        session=64,
        instrument=0,
    )

    assert (production_node.kind, production_node.value) == expected_root
    assert (independent_node.kind, independent_node.value) == expected_root
    assert production_cell == Alpha101Cell(expected)
    assert independent_cell.value == expected
    assert independent_cell.reason is None


def test_unary_binds_outside_power_unless_parenthesized() -> None:
    unparenthesized = parse_formula("-2^2")
    parenthesized = parse_formula("(-2)^2")
    negative_exponent = parse_formula("2^-2")

    assert unparenthesized.canonical() == (
        "unary",
        "-",
        (("binary", "^", (("number", "2", ()), ("number", "2", ()))),),
    )
    assert parenthesized.canonical() == (
        "binary",
        "^",
        (("unary", "-", (("number", "2", ()),)), ("number", "2", ())),
    )
    assert negative_exponent.canonical() == (
        "binary",
        "^",
        (("number", "2", ()), ("unary", "-", (("number", "2", ()),))),
    )


def test_three_value_boolean_and_ternary_are_short_circuiting() -> None:
    unknown = missing(Alpha101Reason.INPUT_MISSING)
    false = Alpha101Cell(0.0)
    true = Alpha101Cell(1.0)
    assert binary(((true,),), ((unknown,),), "||")[0][0] == true
    assert binary(((false,),), ((unknown,),), "||")[0][0] == unknown
    assert binary(((false,),), ((Alpha101Cell(2.0),),), "||")[0][0] == true
    assert binary(((false,),), ((Alpha101Cell(-1.0),),), "||")[0][0] == true
    assert binary(((unknown,),), ((true,),), "||")[0][0] == true
    assert binary(((unknown,),), ((false,),), "||")[0][0] == unknown
    selected = ternary(((true,),), ((Alpha101Cell(7.0),),), ((unknown,),))
    assert selected[0][0] == Alpha101Cell(7.0)


def test_rolling_window_does_not_skip_a_missing_common_session() -> None:
    source = (
        (Alpha101Cell(1.0),),
        (missing(Alpha101Reason.NO_LEGAL_BAR),),
        (Alpha101Cell(3.0),),
    )
    result = rolling((source,), 3, lambda values: sum(values[0]))
    assert result[-1][0].reason == Alpha101Reason.NO_LEGAL_BAR
    overflow = rolling(
        (((Alpha101Cell(1e308),), (Alpha101Cell(1e308),)),),
        2,
        lambda values: sum(values[0]),
    )
    assert overflow[-1][0].reason == Alpha101Reason.NONFINITE


def test_hand_operator_oracle_has_an_independent_content_identity() -> None:
    expected = independent_operator_expected()
    encoded = json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
    digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
    fixture = json.loads(
        Path("tests/fixtures/core/formulaic_alpha101/hand_operators.json").read_text(
            encoding="utf-8"
        )
    )
    assert digest == fixture["expected_output_hash"]
    assert fixture["generator_source_hash"] == generator_source_hash()


def test_frozen_golden_detects_parser_input_mapper_and_operator_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel = full_panel()
    definition = ALPHA101_DEFINITIONS[100]
    golden = json.loads(
        Path("tests/fixtures/core/formulaic_alpha101/golden_full_260d.json").read_text()
    )
    expected = next(
        row
        for row in golden["cells"]
        if row[:2] == [definition.feature_definition_id, panel.instruments[0]]
    )

    def assert_matches() -> None:
        cell = Alpha101Evaluator(panel).evaluate(definition)[-1][0]
        assert cell.state.value == expected[2]
        assert (cell.reason.value if cell.reason else None) == expected[3]
        assert cell.value is not None and expected[4] is not None
        assert math.isclose(cell.value, float.fromhex(expected[4]), rel_tol=1e-12, abs_tol=1e-12)

    assert_matches()
    real_parse = parse_formula

    def broken_parse(_source: str) -> AstNode:
        return real_parse("0")

    monkeypatch.setattr(evaluator_module, "parse_formula", broken_parse)
    with pytest.raises(AssertionError):
        assert_matches()
    monkeypatch.undo()

    real_input = Alpha101Panel.input_matrix

    def broken_input(target: Alpha101Panel, name: str) -> Matrix:
        return real_input(target, "open" if name == "close" else name)

    monkeypatch.setattr(Alpha101Panel, "input_matrix", broken_input)
    with pytest.raises(AssertionError):
        assert_matches()
    monkeypatch.undo()

    real_binary = binary

    def broken_binary(left: Matrix, right: Matrix, operator: str) -> Matrix:
        return left if operator == "/" else real_binary(left, right, operator)

    monkeypatch.setattr(evaluator_module, "binary", broken_binary)
    with pytest.raises(AssertionError):
        assert_matches()
