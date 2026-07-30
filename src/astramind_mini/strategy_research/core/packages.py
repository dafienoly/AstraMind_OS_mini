"""Canonical package declarations shared by all first-release core factors."""

from .contracts import CoreFeaturePackageSpec

ASTRAMIND_F0 = CoreFeaturePackageSpec(
    package_id="astramind-f0-v1",
    canonical_dimension=24,
    authoritative_source="REQ-2026-0007-v2.3.0-section-6",
    data_semantics_version="core-data-semantics-v1",
    universe_version="U0-v1",
)
QLIB_ALPHA158 = CoreFeaturePackageSpec(
    package_id="qlib-alpha158-79633dd",
    canonical_dimension=158,
    authoritative_source="qlib-79633dd9506ea689e5400dea0197717b5b3d74b7",
    data_semantics_version="core-data-semantics-v1",
    universe_version="U0-v1",
)
FORMULAIC_ALPHA101 = CoreFeaturePackageSpec(
    package_id="formulaic-alpha101-v3",
    canonical_dimension=101,
    authoritative_source="arxiv-1601.00991v3",
    data_semantics_version="core-data-semantics-v1",
    universe_version="U0-v1",
)

CORE_FEATURE_PACKAGES = (ASTRAMIND_F0, QLIB_ALPHA158, FORMULAIC_ALPHA101)

__all__ = [
    "ASTRAMIND_F0",
    "CORE_FEATURE_PACKAGES",
    "FORMULAIC_ALPHA101",
    "QLIB_ALPHA158",
]
