"""Canonical package declarations shared by all first-release core factors."""

from types import MappingProxyType

from .contracts import CoreFeaturePackageSpec

ASTRAMIND_F0_FEATURE_ORDER = (
    "EP_TTM",
    "BP",
    "SP_TTM",
    "DY_TTM",
    "ROE_TTM",
    "ROA_TTM",
    "OPERATING_MARGIN_TTM",
    "OCF_TO_NET_INCOME_TTM",
    "ACCRUALS_TO_ASSETS_TTM",
    "DEBT_TO_ASSETS",
    "REVENUE_TTM_YOY",
    "NET_PROFIT_TTM_YOY",
    "OCF_TTM_YOY",
    "MOM_20_5",
    "MOM_60_5",
    "MOM_120_20",
    "INDUSTRY_REL_MOM_60_5",
    "REV_5",
    "RESIDUAL_REV_20",
    "REALIZED_VOL_20",
    "DOWNSIDE_VOL_60",
    "LOG_MEDIAN_AMOUNT_20",
    "TURNOVER_MEAN_20",
    "AMIHUD_20",
)
_ALPHA158_PREFIX = (
    "KMID",
    "KLEN",
    "KMID2",
    "KUP",
    "KUP2",
    "KLOW",
    "KLOW2",
    "KSFT",
    "KSFT2",
    "OPEN0",
    "HIGH0",
    "LOW0",
    "VWAP0",
)
_ALPHA158_ROLLING_FAMILIES = (
    "ROC",
    "MA",
    "STD",
    "BETA",
    "RSQR",
    "RESI",
    "MAX",
    "MIN",
    "QTLU",
    "QTLD",
    "RANK",
    "RSV",
    "IMAX",
    "IMIN",
    "IMXD",
    "CORR",
    "CORD",
    "CNTP",
    "CNTN",
    "CNTD",
    "SUMP",
    "SUMN",
    "SUMD",
    "VMA",
    "VSTD",
    "WVMA",
    "VSUMP",
    "VSUMN",
    "VSUMD",
)
QLIB_ALPHA158_FEATURE_ORDER = _ALPHA158_PREFIX + tuple(
    f"{family}{window}"
    for family in _ALPHA158_ROLLING_FAMILIES
    for window in (5, 10, 20, 30, 60)
)
FORMULAIC_ALPHA101_FEATURE_ORDER = tuple(
    f"alpha101_{ordinal:03d}" for ordinal in range(1, 102)
)

ASTRAMIND_F0 = CoreFeaturePackageSpec(
    package_id="astramind-f0-v1",
    canonical_dimension=24,
    authoritative_source="REQ-2026-0007-v2.3.0-section-6",
    data_semantics_version="core-data-semantics-v1",
    universe_version="U0-v1",
    required_definition_registry_hash=(
        "sha256:5fd8435ecfd1dee75ca078a6aed7cfd47a257efa427394766938ba1fa5598b9b"
    ),
)
QLIB_ALPHA158 = CoreFeaturePackageSpec(
    package_id="qlib-alpha158-79633dd",
    canonical_dimension=158,
    authoritative_source="qlib-79633dd9506ea689e5400dea0197717b5b3d74b7",
    data_semantics_version="core-data-semantics-v1",
    universe_version="U0-v1",
    required_definition_registry_hash=(
        "sha256:002151c6f808dc503b292caa604435f634d69672193288535f3fec504dd61c04"
    ),
)
FORMULAIC_ALPHA101 = CoreFeaturePackageSpec(
    package_id="formulaic-alpha101-v3",
    canonical_dimension=101,
    authoritative_source="arxiv-1601.00991v3",
    data_semantics_version="core-data-semantics-v1",
    universe_version="U0-v1",
    required_definition_registry_hash=(
        "sha256:6895ebea945ed4c95e43d8fd7d19cd97a77fb3a32f7868133c320a5f9ebde1c5"
    ),
)

CORE_FEATURE_PACKAGES = (ASTRAMIND_F0, QLIB_ALPHA158, FORMULAIC_ALPHA101)
CORE_FEATURE_ORDERS = MappingProxyType(
    {
        ASTRAMIND_F0.package_id: ASTRAMIND_F0_FEATURE_ORDER,
        QLIB_ALPHA158.package_id: QLIB_ALPHA158_FEATURE_ORDER,
        FORMULAIC_ALPHA101.package_id: FORMULAIC_ALPHA101_FEATURE_ORDER,
    }
)

__all__ = [
    "ASTRAMIND_F0",
    "ASTRAMIND_F0_FEATURE_ORDER",
    "CORE_FEATURE_ORDERS",
    "CORE_FEATURE_PACKAGES",
    "FORMULAIC_ALPHA101",
    "FORMULAIC_ALPHA101_FEATURE_ORDER",
    "QLIB_ALPHA158",
    "QLIB_ALPHA158_FEATURE_ORDER",
]
