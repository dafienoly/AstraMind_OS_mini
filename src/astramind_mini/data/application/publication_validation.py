"""Cross-dataset publication checks for the bounded production snapshot."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from ..contracts import (
    AdjustmentFactorObservation,
    DailyBarObservation,
    SecurityMasterObservation,
)


def validate_market_coverage(
    securities: Sequence[SecurityMasterObservation],
    daily: Sequence[DailyBarObservation],
    factors: Sequence[AdjustmentFactorObservation],
    trade_date: date,
) -> int:
    if {row.trade_date for row in daily} != {trade_date}:
        raise ValueError("日线包含目标交易日之外的数据")
    if {row.trade_date for row in factors} != {trade_date}:
        raise ValueError("复权因子包含目标交易日之外的数据")

    security_ids = {row.instrument_id for row in securities}
    daily_ids = {row.instrument_id for row in daily}
    factor_ids = {row.instrument_id for row in factors}
    unknown_daily = daily_ids - security_ids
    if unknown_daily:
        raise ValueError(f"日线存在 {len(unknown_daily)} 个证券主表未知身份")
    missing_factors = daily_ids - factor_ids
    if missing_factors:
        raise ValueError(f"日线存在 {len(missing_factors)} 个缺失复权因子的证券")
    return len(factor_ids - daily_ids)


__all__ = ["validate_market_coverage"]
