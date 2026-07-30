"""Assertions that compare production results with frozen independent golden cells."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import cast

from astramind_mini.strategy_research.core.feature_output import CoreRawFeatureEnvelope
from astramind_mini.strategy_research.core.formulaic_alpha101.evaluator import (
    Alpha101Evaluator,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.inputs import Alpha101Panel
from astramind_mini.strategy_research.core.formulaic_alpha101.reasons import Alpha101Reason
from astramind_mini.strategy_research.core.formulaic_alpha101.registry import (
    ALPHA101_DEFINITIONS,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.values import Alpha101Cell

FIXTURES = Path(__file__).parent
GoldenCell = tuple[str, str | None, str | None]


def golden_cells(name: str) -> dict[tuple[str, str], GoldenCell]:
    payload = json.loads((FIXTURES / f"golden_{name}.json").read_text(encoding="utf-8"))
    rows = cast(list[list[str | None]], payload["cells"])
    result = {}
    for row in rows:
        feature_id, instrument_id, state, reason, value_hex = row
        assert feature_id is not None and instrument_id is not None and state is not None
        result[feature_id, instrument_id] = state, reason, value_hex
    return result


def assert_cell_matches_golden(actual: Alpha101Cell, expected: GoldenCell) -> None:
    state, reason, value_hex = expected
    assert actual.state.value == state
    assert (actual.reason.value if actual.reason else None) == reason
    if value_hex is None:
        assert actual.value is None
    else:
        assert actual.value is not None
        assert math.isclose(actual.value, float.fromhex(value_hex), rel_tol=1e-12, abs_tol=1e-12)


def assert_evaluator_matches_golden(
    panel: Alpha101Panel,
    evaluator: Alpha101Evaluator,
    name: str,
) -> None:
    expected = golden_cells(name)
    for definition in ALPHA101_DEFINITIONS:
        row = evaluator.evaluate(definition)[-1]
        for index, instrument in enumerate(panel.instruments):
            assert_cell_matches_golden(
                row[index],
                expected[definition.feature_definition_id, instrument],
            )


def assert_envelope_matches_golden(envelope: CoreRawFeatureEnvelope, name: str) -> None:
    expected = golden_cells(name)
    for row in envelope.rows:
        cell = Alpha101Cell(
            row.value_raw,
            Alpha101Reason(row.missing_reason_code) if row.missing_reason_code else None,
        )
        assert_cell_matches_golden(
            cell,
            expected[row.feature_definition_id, row.instrument_id],
        )


__all__ = [
    "assert_cell_matches_golden",
    "assert_envelope_matches_golden",
    "assert_evaluator_matches_golden",
    "golden_cells",
]
