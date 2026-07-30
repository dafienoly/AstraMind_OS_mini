"""Frozen Qlib Alpha158 names, formulas, and source identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ..packages import QLIB_ALPHA158, QLIB_ALPHA158_FEATURE_ORDER

PACKAGE_ID = "qlib-alpha158-79633dd"
QLIB_COMMIT = "79633dd9506ea689e5400dea0197717b5b3d74b7"
DATA_SEMANTICS_VERSION = "core-data-semantics-v1"
DEFINITION_VERSION = "1.0.0"
WINDOWS = (5, 10, 20, 30, 60)
SOURCE_SHA256 = {
    "qlib/contrib/data/loader.py": (
        "814b7f7ab3d418ae3c87ce352220080b239eba2670eac9e38376b794be4075cb"
    ),
    "qlib/contrib/data/handler.py": (
        "b621481c6009c39066c67c71390fd2bea635f56daf9f2c4e38817eff268e3232"
    ),
    "qlib/data/ops.py": "6f648355725a85a9f17528d864281fc065f8a4f887261a9909f7495d5db42760",
    "qlib/data/_libs/rolling.pyx": (
        "58b2e418a78558135cb1ecad88bfcff68cae98b2bb2695d8d2fade8b30c5dbf1"
    ),
}
EXPECTED_NAMES_SHA256 = "d5f52c2d75ea900ab29f4742eeb59d9692254ba7307ad36a807012db7d680e13"
EXPECTED_FIELDS_SHA256 = "05943b7d14e82ab604fe76938465589014c6e89b51f09116a2805c59080678a3"
EXPECTED_PAIRS_SHA256 = "b1154a5b310ec5f8ead6ca064c06ae4a1121dc1c9a0d4ff7dcd00efcf20704e5"
EXPECTED_COMPUTATION_MANIFEST_HASH = (
    "sha256:9c6871c861793952f6693e0c209b28a7179eb3df0c38d5e2a9ff40c6ddc5a5c6"
)

_PREFIX_FIELDS = (
    "($close-$open)/$open",
    "($high-$low)/$open",
    "($close-$open)/($high-$low+1e-12)",
    "($high-Greater($open, $close))/$open",
    "($high-Greater($open, $close))/($high-$low+1e-12)",
    "(Less($open, $close)-$low)/$open",
    "(Less($open, $close)-$low)/($high-$low+1e-12)",
    "(2*$close-$high-$low)/$open",
    "(2*$close-$high-$low)/($high-$low+1e-12)",
    "$open/$close",
    "$high/$close",
    "$low/$close",
    "$vwap/$close",
)


def _rolling_fields(window: int) -> tuple[str, ...]:
    d = window
    return (
        f"Ref($close, {d})/$close",
        f"Mean($close, {d})/$close",
        f"Std($close, {d})/$close",
        f"Slope($close, {d})/$close",
        f"Rsquare($close, {d})",
        f"Resi($close, {d})/$close",
        f"Max($high, {d})/$close",
        f"Min($low, {d})/$close",
        f"Quantile($close, {d}, 0.8)/$close",
        f"Quantile($close, {d}, 0.2)/$close",
        f"Rank($close, {d})",
        (f"($close-Min($low, {d}))/(Max($high, {d})-Min($low, {d})+1e-12)"),
        f"IdxMax($high, {d})/{d}",
        f"IdxMin($low, {d})/{d}",
        f"(IdxMax($high, {d})-IdxMin($low, {d}))/{d}",
        f"Corr($close, Log($volume+1), {d})",
        f"Corr($close/Ref($close,1), Log($volume/Ref($volume, 1)+1), {d})",
        f"Mean($close>Ref($close, 1), {d})",
        f"Mean($close<Ref($close, 1), {d})",
        (f"Mean($close>Ref($close, 1), {d})-Mean($close<Ref($close, 1), {d})"),
        (
            f"Sum(Greater($close-Ref($close, 1), 0), {d})/"
            f"(Sum(Abs($close-Ref($close, 1)), {d})+1e-12)"
        ),
        (
            f"Sum(Greater(Ref($close, 1)-$close, 0), {d})/"
            f"(Sum(Abs($close-Ref($close, 1)), {d})+1e-12)"
        ),
        (
            f"(Sum(Greater($close-Ref($close, 1), 0), {d})"
            f"-Sum(Greater(Ref($close, 1)-$close, 0), {d}))/"
            f"(Sum(Abs($close-Ref($close, 1)), {d})+1e-12)"
        ),
        f"Mean($volume, {d})/($volume+1e-12)",
        f"Std($volume, {d})/($volume+1e-12)",
        (
            f"Std(Abs($close/Ref($close, 1)-1)*$volume, {d})/"
            f"(Mean(Abs($close/Ref($close, 1)-1)*$volume, {d})+1e-12)"
        ),
        (
            f"Sum(Greater($volume-Ref($volume, 1), 0), {d})/"
            f"(Sum(Abs($volume-Ref($volume, 1)), {d})+1e-12)"
        ),
        (
            f"Sum(Greater(Ref($volume, 1)-$volume, 0), {d})/"
            f"(Sum(Abs($volume-Ref($volume, 1)), {d})+1e-12)"
        ),
        (
            f"(Sum(Greater($volume-Ref($volume, 1), 0), {d})"
            f"-Sum(Greater(Ref($volume, 1)-$volume, 0), {d}))/"
            f"(Sum(Abs($volume-Ref($volume, 1)), {d})+1e-12)"
        ),
    )


_ROLLING_BY_WINDOW = tuple(_rolling_fields(window) for window in WINDOWS)
QLIB_ALPHA158_FIELDS = _PREFIX_FIELDS + tuple(
    fields[family_index] for family_index in range(29) for fields in _ROLLING_BY_WINDOW
)
QLIB_ALPHA158_NAMES = QLIB_ALPHA158_FEATURE_ORDER
QLIB_ALPHA158_PAIRS = tuple(zip(QLIB_ALPHA158_NAMES, QLIB_ALPHA158_FIELDS, strict=True))


def _json_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


NAMES_SHA256 = _json_sha256(QLIB_ALPHA158_NAMES)
FIELDS_SHA256 = _json_sha256(QLIB_ALPHA158_FIELDS)
PAIRS_SHA256 = _json_sha256(QLIB_ALPHA158_PAIRS)


def canonical_alpha158_computation_manifest() -> dict[str, object]:
    """Return the complete, package-owned formula and operator identity."""
    return {
        "schema": "qlib-alpha158-computation-manifest-v3",
        "package_id": PACKAGE_ID,
        "qlib_commit": QLIB_COMMIT,
        "source_sha256": dict(SOURCE_SHA256),
        "data_semantics_version": DATA_SEMANTICS_VERSION,
        "definition_version": DEFINITION_VERSION,
        "expression_pairs": QLIB_ALPHA158_PAIRS,
        "windows": WINDOWS,
        "input_semantics": (
            "ohlc=continuous_research_price_index",
            "volume=lots_100_shares",
            "vwap=raw_amount_cny/raw_volume_shares_scaled_to_research_close_index",
            "calendar=CoreInputSnapshot.common_sessions_exact_sequence",
            "dtype=little_endian_float64",
        ),
        "operator_semantics": (
            "Ref=fixed_row_shift",
            "OrdinaryRolling=pandas-2.2.3-min_periods_1-ignore_NaN_posInf_negInf",
            "Std=sample_ddof_1",
            "Quantile=linear_interpolation",
            "Rank=current_percentile_average_ties-nonfinite_current_missing",
            "IdxMaxIdxMin=raw_numpy_arg_1_based_earliest_tie-no_nonfinite_filter",
            "GreaterLess=numpy_maximum_minimum",
            "SlopeRsquareResi=rolling.pyx-cross_row-state-machine-operation-order",
            "Rsquare=rolling.pyx-plus-pandas_std_isclose_atol_2e-5",
            "Corr=pandas-2.2.3-paired-Kahan-mean-Welford-var"
            "-Qlib-original-operand-std-isclose-atol_2e-5",
            "BooleanCompare=NaN_comparison_false",
            "Division=IEEE754-only_formula_epsilon",
            "PublicNonfinite=missing_alpha158_non_finite_formula_result",
        ),
    }


def alpha158_computation_manifest_hash() -> str:
    encoded = json.dumps(
        canonical_alpha158_computation_manifest(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    actual = "sha256:" + hashlib.sha256(encoded).hexdigest()
    if actual != EXPECTED_COMPUTATION_MANIFEST_HASH:
        raise RuntimeError("Alpha158 computation manifest identity mismatch")
    return actual


@dataclass(frozen=True)
class Alpha158Manifest:
    package_id: str = PACKAGE_ID
    qlib_commit: str = QLIB_COMMIT
    data_semantics_version: str = DATA_SEMANTICS_VERSION
    definition_version: str = DEFINITION_VERSION
    required_definition_registry_hash: str = QLIB_ALPHA158.required_definition_registry_hash
    names_sha256: str = NAMES_SHA256
    fields_sha256: str = FIELDS_SHA256
    pairs_sha256: str = PAIRS_SHA256
    names: tuple[str, ...] = QLIB_ALPHA158_NAMES
    fields: tuple[str, ...] = QLIB_ALPHA158_FIELDS


ALPHA158_MANIFEST = Alpha158Manifest()


def validate_frozen_manifest() -> None:
    expected = (
        158,
        158,
        EXPECTED_NAMES_SHA256,
        EXPECTED_FIELDS_SHA256,
        EXPECTED_PAIRS_SHA256,
    )
    actual = (
        len(QLIB_ALPHA158_NAMES),
        len(set(QLIB_ALPHA158_NAMES)),
        NAMES_SHA256,
        FIELDS_SHA256,
        PAIRS_SHA256,
    )
    if actual != expected:
        raise RuntimeError(f"Alpha158 manifest identity mismatch: {actual!r}")


__all__ = [
    "ALPHA158_MANIFEST",
    "DATA_SEMANTICS_VERSION",
    "DEFINITION_VERSION",
    "EXPECTED_COMPUTATION_MANIFEST_HASH",
    "EXPECTED_FIELDS_SHA256",
    "EXPECTED_NAMES_SHA256",
    "EXPECTED_PAIRS_SHA256",
    "FIELDS_SHA256",
    "NAMES_SHA256",
    "PACKAGE_ID",
    "PAIRS_SHA256",
    "QLIB_ALPHA158_FIELDS",
    "QLIB_ALPHA158_NAMES",
    "QLIB_ALPHA158_PAIRS",
    "QLIB_COMMIT",
    "SOURCE_SHA256",
    "WINDOWS",
    "alpha158_computation_manifest_hash",
    "canonical_alpha158_computation_manifest",
    "validate_frozen_manifest",
]
