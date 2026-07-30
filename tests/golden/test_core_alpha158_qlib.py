from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import numpy as np

from astramind_mini.strategy_research.core.alpha158 import (
    FIELDS_SHA256,
    NAMES_SHA256,
    PAIRS_SHA256,
    QLIB_ALPHA158_FIELDS,
    QLIB_ALPHA158_NAMES,
    QLIB_COMMIT,
    SOURCE_SHA256,
    calculate_alpha158,
)
from tests.unit.test_core_alpha158_support import (
    INSTRUMENTS,
    batch_from_cube,
    common_dates,
    load_golden_cube,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "core" / "alpha158"


def test_frozen_manifest_and_provenance_are_byte_identified() -> None:
    manifest = _json("manifest.json")
    provenance = _json("provenance.json")

    assert tuple(manifest["names"]) == QLIB_ALPHA158_NAMES
    assert tuple(manifest["fields"]) == QLIB_ALPHA158_FIELDS
    assert manifest["names_sha256"] == NAMES_SHA256
    assert manifest["fields_sha256"] == FIELDS_SHA256
    assert manifest["pairs_sha256"] == PAIRS_SHA256
    assert manifest["qlib_commit"] == QLIB_COMMIT
    assert manifest["source_sha256"] == SOURCE_SHA256
    assert provenance["qlib_commit"] == QLIB_COMMIT
    assert provenance["source_sha256"] == SOURCE_SHA256
    assert (
        provenance["computation_manifest_hash"]
        == "sha256:9c6871c861793952f6693e0c209b28a7179eb3df0c38d5e2a9ff40c6ddc5a5c6"
    )
    assert provenance["input_layout"]["instrument_order"] == list(INSTRUMENTS)
    assert provenance["input_layout"]["market_date_order"] == [
        value.isoformat() for value in common_dates()
    ]
    assert provenance["reference_status"] == (
        "independent fixed-Qlib runtime oracle with compiled rolling.pyx"
    )
    assert (
        provenance["reference_generator_sha256"]
        == "7c4428980f86e3ac8b070a88b2be994fd28227946253587a1955276c47936950"
    )
    assert provenance["reference_environment"] == {
        "python": "3.12.13",
        "python_compiler": "Clang 22.1.3",
        "numpy": "1.26.4",
        "pandas": "2.2.3",
        "scipy": "1.15.3",
        "cython": "3.1.2",
        "c_compiler": "GCC (Ubuntu 15.2.0-16ubuntu1) 15.2.0",
        "platform": "Linux WSL2 x86_64",
        "pyqlib": "source checkout at fixed commit; rolling.pyx compiled and loaded",
        "compiled_rolling_extension_sha256": (
            "786bf98675f9142ffbbea66481aa082d857547533b2f9f2f1cb793c3ce0bcc57"
        ),
    }
    _assert_generator_identities(provenance)
    _assert_auxiliary_fixture_identities(provenance)
    assert "bootstrap_generation_command" not in provenance
    manifest_hash = hashlib.sha256(
        json.dumps(
            manifest,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert manifest_hash == provenance["logical_sha256"]["manifest"]


def _assert_generator_identities(provenance: dict[str, Any]) -> None:
    generator = FIXTURE / provenance["reference_generator_source"]
    generator_hash = hashlib.sha256(generator.read_bytes()).hexdigest()
    assert generator_hash == provenance["logical_sha256"]["reference_generator_source_file"]
    assert generator_hash == provenance["reference_generator_sha256"]
    corr_generator = FIXTURE / provenance["corr_reference_generator_source"]
    corr_generator_hash = hashlib.sha256(corr_generator.read_bytes()).hexdigest()
    assert corr_generator_hash == provenance["corr_reference_generator_sha256"]
    assert (
        corr_generator_hash == provenance["logical_sha256"]["corr_reference_generator_source_file"]
    )
    assert (
        hashlib.sha256((FIXTURE / "corr_nonfinite_oracle.json").read_bytes()).hexdigest()
        == (provenance["logical_sha256"]["corr_nonfinite_oracle_file"])
    )


def _assert_auxiliary_fixture_identities(provenance: dict[str, Any]) -> None:
    assert (
        hashlib.sha256((FIXTURE / "wvma_overflow_oracle.json").read_bytes()).hexdigest()
        == (provenance["logical_sha256"]["wvma_overflow_oracle_file"])
    )
    assert (
        hashlib.sha256((FIXTURE / "regression_counterexample.npy").read_bytes()).hexdigest()
        == (provenance["logical_sha256"]["regression_counterexample_file"])
    )
    assert (
        _float_hash(np.load(FIXTURE / "corr_inputs.npy", allow_pickle=False))
        == (provenance["logical_sha256"]["corr_inputs"])
    )
    assert (
        _float_hash(np.load(FIXTURE / "corr_expected.npy", allow_pickle=False))
        == (provenance["logical_sha256"]["corr_expected"])
    )
    for filename, identity in (
        ("corr_windows.npy", "corr_windows"),
        ("corr_expected_nonfinite_mask.npy", "corr_expected_nonfinite_mask"),
    ):
        values = np.load(FIXTURE / filename, allow_pickle=False)
        assert (
            hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()
            == (provenance["logical_sha256"][identity])
        )


def test_local_numpy_port_matches_the_fixed_3_by_75_by_158_golden() -> None:
    inputs = load_golden_cube(FIXTURE)
    expected = np.load(FIXTURE / "expected.npy", allow_pickle=False)
    expected_mask = np.load(
        FIXTURE / "expected_nonfinite_mask.npy",
        allow_pickle=False,
    )
    provenance = _json("provenance.json")

    assert inputs.shape == (3, 75, 6)
    assert expected.shape == (3, 75, 158)
    assert expected_mask.shape == expected.shape
    assert inputs.dtype.str == expected.dtype.str == "<f8"
    assert inputs.flags.c_contiguous and expected.flags.c_contiguous
    assert _float_hash(inputs) == provenance["logical_sha256"]["inputs"]
    assert _float_hash(expected) == provenance["logical_sha256"]["expected"]
    assert (
        hashlib.sha256(np.ascontiguousarray(expected_mask).tobytes()).hexdigest()
        == provenance["logical_sha256"]["expected_nonfinite_mask"]
    )

    actual = calculate_alpha158(batch_from_cube(inputs, dates=common_dates()))
    np.testing.assert_array_equal(actual.nonfinite_mask, expected_mask)
    finite = expected_mask == 0
    np.testing.assert_allclose(
        actual.values[finite],
        expected[finite],
        rtol=1e-9,
        atol=1e-9,
    )
    discrete = tuple(
        index
        for index, name in enumerate(actual.feature_names)
        if name.startswith(("RANK", "IMAX", "IMIN", "IMXD", "CNTP", "CNTN", "CNTD"))
    )
    for index in discrete:
        mask = expected_mask[:, :, index] == 0
        np.testing.assert_array_equal(
            actual.values[:, :, index][mask],
            expected[:, :, index][mask],
        )


def test_golden_error_location_is_below_the_fixed_tolerance() -> None:
    expected = np.load(FIXTURE / "expected.npy", allow_pickle=False)
    actual = calculate_alpha158(
        batch_from_cube(load_golden_cube(FIXTURE), dates=common_dates())
    ).values
    finite = np.isfinite(actual) & np.isfinite(expected)
    difference = np.abs(actual - expected)
    safe_expected = np.maximum(np.abs(expected), np.finfo(np.float64).tiny)
    relative = difference / safe_expected
    tolerance = 1e-9 + 1e-9 * np.abs(expected)
    assert np.all(difference[finite] <= tolerance[finite])
    assert np.nanmax(relative[finite & (np.abs(expected) >= 1.0)]) <= 1e-9


def _json(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((FIXTURE / name).read_text(encoding="utf-8")),
    )


def _float_hash(values: np.ndarray[Any, np.dtype[np.float64]]) -> str:
    canonical = np.array(values, dtype="<f8", order="C", copy=True)
    canonical[np.isnan(canonical)] = np.float64(np.nan)
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()
