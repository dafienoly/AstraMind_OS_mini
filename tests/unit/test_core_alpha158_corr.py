from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from astramind_mini.strategy_research.core.alpha158.rolling import rolling_corr

FIXTURE = Path(__file__).parents[1] / "fixtures" / "core" / "alpha158"


def test_corr_matches_1000_case_fixed_pandas_qlib_oracle() -> None:
    inputs = np.load(FIXTURE / "corr_inputs.npy", allow_pickle=False)
    windows = np.load(FIXTURE / "corr_windows.npy", allow_pickle=False)
    expected = np.load(FIXTURE / "corr_expected.npy", allow_pickle=False)
    expected_mask = np.load(
        FIXTURE / "corr_expected_nonfinite_mask.npy",
        allow_pickle=False,
    )
    oracle: dict[str, Any] = json.loads(
        (FIXTURE / "corr_nonfinite_oracle.json").read_text(encoding="utf-8")
    )

    actual = np.stack(
        tuple(
            rolling_corr(inputs[index, 0], inputs[index, 1], int(windows[index]))
            for index in range(len(inputs))
        )
    )
    actual_mask = _nonfinite_mask(actual)

    assert inputs.shape == (oracle["case_count"], 2, oracle["length"])
    assert oracle["pandas"] == "2.2.3"
    np.testing.assert_array_equal(actual_mask, expected_mask)
    np.testing.assert_array_equal(actual, expected)
    assert actual_mask[:4, 4].tolist() == [2, 3, 3, 2]
    assert oracle["case_final_classifications"] == [
        "positive_infinity",
        "negative_infinity",
        "negative_infinity",
        "positive_infinity",
    ]


def _nonfinite_mask(values: np.ndarray[Any, np.dtype[np.float64]]) -> np.ndarray:
    result = np.zeros(values.shape, dtype=np.uint8)
    result[np.isnan(values)] = 1
    result[np.isposinf(values)] = 2
    result[np.isneginf(values)] = 3
    return result
