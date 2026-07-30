"""Public entry point for the frozen, NumPy-only Qlib Alpha158 package."""

from .calculator import (
    FINITE,
    MISSING_REASON,
    NAN,
    NEGATIVE_INFINITY,
    POSITIVE_INFINITY,
    Alpha158Computation,
    build_alpha158_raw_envelope,
    calculate_alpha158,
    calculate_alpha158_in_chunks,
)
from .definitions import (
    ALPHA158_MANIFEST,
    EXPECTED_COMPUTATION_MANIFEST_HASH,
    FIELDS_SHA256,
    NAMES_SHA256,
    PAIRS_SHA256,
    QLIB_ALPHA158_FIELDS,
    QLIB_ALPHA158_NAMES,
    QLIB_COMMIT,
    SOURCE_SHA256,
    alpha158_computation_manifest_hash,
)
from .inputs import (
    VOLUME_UNIT,
    Alpha158BatchInput,
    Alpha158InputError,
    Alpha158InstrumentInput,
)

__all__ = [
    "ALPHA158_MANIFEST",
    "EXPECTED_COMPUTATION_MANIFEST_HASH",
    "FIELDS_SHA256",
    "FINITE",
    "MISSING_REASON",
    "NAMES_SHA256",
    "NAN",
    "NEGATIVE_INFINITY",
    "PAIRS_SHA256",
    "POSITIVE_INFINITY",
    "QLIB_ALPHA158_FIELDS",
    "QLIB_ALPHA158_NAMES",
    "QLIB_COMMIT",
    "SOURCE_SHA256",
    "VOLUME_UNIT",
    "Alpha158BatchInput",
    "Alpha158Computation",
    "Alpha158InputError",
    "Alpha158InstrumentInput",
    "alpha158_computation_manifest_hash",
    "build_alpha158_raw_envelope",
    "calculate_alpha158",
    "calculate_alpha158_in_chunks",
]
