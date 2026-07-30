"""Frozen astramind-f0-v1 formula registry."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from ...application.identity import research_hash
from ..feature_identity import DefinitionRow, canonical_definition_registry_hash
from ..packages import ASTRAMIND_F0, ASTRAMIND_F0_FEATURE_ORDER
from .computation_semantics import (
    F0_FINANCIAL_COMPUTATION_SEMANTICS,
    F0_MARKET_OPERATOR_SEMANTICS,
)
from .reasons import F0Reason

Direction = Literal["positive", "negative"]
Applicability = Literal["corporate_only", "all_u0", "strict_sw_l1"]


@dataclass(frozen=True)
class F0Definition:
    ordinal: int
    feature_definition_id: str
    feature_definition_version: str
    family: str
    direction: Direction
    formula: str
    inputs: tuple[str, ...]
    maximum_lookback: int
    applicability: Applicability
    failure_reason_codes: tuple[str, ...]


def _definition(
    feature_id: str,
    family: str,
    direction: Direction,
    formula: str,
    inputs: tuple[str, ...],
    lookback: int,
    applicability: Applicability = "corporate_only",
) -> F0Definition:
    return F0Definition(
        ordinal=len(_definitions),
        feature_definition_id=feature_id,
        feature_definition_version="1.0.0",
        family=family,
        direction=direction,
        formula=formula,
        inputs=inputs,
        maximum_lookback=lookback,
        applicability=applicability,
        failure_reason_codes=tuple(reason.value for reason in F0Reason),
    )


_definitions: list[F0Definition] = []
for args in (
    (
        "EP_TTM",
        "value",
        "positive",
        "parent_net_profit_ttm / total_market_cap",
        ("financial", "market_cap"),
        504,
    ),
    (
        "BP",
        "value",
        "positive",
        "parent_equity / total_market_cap",
        ("financial", "market_cap"),
        252,
    ),
    (
        "SP_TTM",
        "value",
        "positive",
        "revenue_ttm / total_market_cap",
        ("financial", "market_cap"),
        504,
    ),
    (
        "DY_TTM",
        "value",
        "positive",
        "cash_dividend_per_share_12m / research_close",
        ("dividend", "research_close"),
        252,
    ),
    (
        "ROE_TTM",
        "profitability",
        "positive",
        "parent_net_profit_ttm / average_parent_equity",
        ("financial",),
        504,
    ),
    (
        "ROA_TTM",
        "profitability",
        "positive",
        "net_profit_ttm / average_total_assets",
        ("financial",),
        504,
    ),
    (
        "OPERATING_MARGIN_TTM",
        "profitability",
        "positive",
        "operating_profit_ttm / revenue_ttm",
        ("financial",),
        504,
    ),
    (
        "OCF_TO_NET_INCOME_TTM",
        "quality",
        "positive",
        "operating_cash_flow_ttm / net_profit_ttm",
        ("financial",),
        504,
    ),
    (
        "ACCRUALS_TO_ASSETS_TTM",
        "quality",
        "negative",
        "(net_profit_ttm - operating_cash_flow_ttm) / average_total_assets",
        ("financial",),
        504,
    ),
    (
        "DEBT_TO_ASSETS",
        "quality",
        "negative",
        "total_liabilities / total_assets",
        ("financial",),
        252,
    ),
    (
        "REVENUE_TTM_YOY",
        "growth",
        "positive",
        "revenue_ttm / prior_year_revenue_ttm - 1",
        ("financial",),
        504,
    ),
    (
        "NET_PROFIT_TTM_YOY",
        "growth",
        "positive",
        "parent_net_profit_ttm / prior_year_parent_net_profit_ttm - 1",
        ("financial",),
        504,
    ),
    (
        "OCF_TTM_YOY",
        "growth",
        "positive",
        "operating_cash_flow_ttm / prior_year_operating_cash_flow_ttm - 1",
        ("financial",),
        504,
    ),
    (
        "MOM_20_5",
        "momentum",
        "positive",
        "close[T-5] / close[T-20] - 1",
        ("research_close",),
        20,
        "all_u0",
    ),
    (
        "MOM_60_5",
        "momentum",
        "positive",
        "close[T-5] / close[T-60] - 1",
        ("research_close",),
        60,
        "all_u0",
    ),
    (
        "MOM_120_20",
        "momentum",
        "positive",
        "close[T-20] / close[T-120] - 1",
        ("research_close",),
        120,
        "all_u0",
    ),
    (
        "INDUSTRY_REL_MOM_60_5",
        "momentum",
        "positive",
        "MOM_60_5 - contemporaneous_SW_L1_equal_weight_return",
        ("research_close", "point_in_time_sw_l1", "historical_u0"),
        60,
        "strict_sw_l1",
    ),
    (
        "REV_5",
        "reversal",
        "positive",
        "-(close[T] / close[T-5] - 1)",
        ("research_close",),
        5,
        "all_u0",
    ),
    (
        "RESIDUAL_REV_20",
        "reversal",
        "positive",
        "-sum(OLS residuals over 20 sessions)",
        ("research_close", "point_in_time_sw_l1", "historical_u0"),
        20,
        "strict_sw_l1",
    ),
    (
        "REALIZED_VOL_20",
        "low_volatility",
        "negative",
        "sqrt(252) * sample_std(log_return, ddof=1)",
        ("research_close",),
        20,
        "all_u0",
    ),
    (
        "DOWNSIDE_VOL_60",
        "low_volatility",
        "negative",
        "sqrt(252 * mean(min(simple_return, 0)^2))",
        ("research_close",),
        60,
        "all_u0",
    ),
    (
        "LOG_MEDIAN_AMOUNT_20",
        "liquidity",
        "positive",
        "log(1 + median(raw_amount, 20))",
        ("raw_amount",),
        20,
        "all_u0",
    ),
    (
        "TURNOVER_MEAN_20",
        "liquidity",
        "positive",
        "mean(raw_turnover_rate, 20)",
        ("raw_turnover_rate",),
        20,
        "all_u0",
    ),
    (
        "AMIHUD_20",
        "liquidity",
        "negative",
        "log(1 + 1e8 * mean(abs(simple_return) / raw_amount, 20))",
        ("research_close", "raw_amount"),
        20,
        "all_u0",
    ),
):
    _definitions.append(_definition(*args))

F0_DEFINITIONS = tuple(_definitions)
F0_DEFINITION_REGISTRY_HASH = canonical_definition_registry_hash(
    ASTRAMIND_F0_FEATURE_ORDER,
    cast(Sequence[DefinitionRow], F0_DEFINITIONS),
)

def full_definition_manifest_hash(
    definitions: Sequence[F0Definition],
    *,
    financial_semantics: object = F0_FINANCIAL_COMPUTATION_SEMANTICS,
    market_semantics: object = F0_MARKET_OPERATOR_SEMANTICS,
) -> str:
    """Hash every semantic field plus package, REQ and implementation identity."""
    return research_hash(
        {
            "schema": "astramind-f0-full-definition-manifest-v1",
            "package_id": ASTRAMIND_F0.package_id,
            "authoritative_source": ASTRAMIND_F0.authoritative_source,
            "implementation_identity": "astramind-mini:wp-0071a:f0-formulas-v1",
            "data_semantics_version": ASTRAMIND_F0.data_semantics_version,
            "universe_version": ASTRAMIND_F0.universe_version,
            "legacy_registry_hash": F0_DEFINITION_REGISTRY_HASH,
            "definitions": tuple(definitions),
            "financial_computation_semantics": financial_semantics,
            "market_operator_semantics": market_semantics,
        }
    )


F0_FULL_DEFINITION_MANIFEST_HASH = full_definition_manifest_hash(F0_DEFINITIONS)
_REQUIRED_FULL_DEFINITION_MANIFEST_HASH = (
    "sha256:a404abe527f5b50c66c974d4520529a1ec0a4aaa3049daea28fea66900f6900f"
)


def validate_f0_definition_manifest(
    definitions: Sequence[F0Definition],
    *,
    financial_semantics: object = F0_FINANCIAL_COMPUTATION_SEMANTICS,
    market_semantics: object = F0_MARKET_OPERATOR_SEMANTICS,
) -> str:
    manifest_hash = full_definition_manifest_hash(
        definitions,
        financial_semantics=financial_semantics,
        market_semantics=market_semantics,
    )
    if manifest_hash != _REQUIRED_FULL_DEFINITION_MANIFEST_HASH:
        raise ValueError("astramind-f0-v1 full definition manifest drifted")
    return manifest_hash


if tuple(item.feature_definition_id for item in F0_DEFINITIONS) != ASTRAMIND_F0_FEATURE_ORDER:
    raise RuntimeError("astramind-f0-v1 definition order drifted")
if ASTRAMIND_F0.required_definition_registry_hash != F0_DEFINITION_REGISTRY_HASH:
    raise RuntimeError("astramind-f0-v1 registry hash drifted")
validate_f0_definition_manifest(F0_DEFINITIONS)

__all__ = [
    "F0_DEFINITIONS",
    "F0_DEFINITION_REGISTRY_HASH",
    "F0_FINANCIAL_COMPUTATION_SEMANTICS",
    "F0_FULL_DEFINITION_MANIFEST_HASH",
    "F0_MARKET_OPERATOR_SEMANTICS",
    "F0Definition",
    "full_definition_manifest_hash",
    "validate_f0_definition_manifest",
]
