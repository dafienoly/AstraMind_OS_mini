from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from astramind_mini.data.application.normalization import (
    normalize_adjustment_factors,
    normalize_daily_bars,
    normalize_daily_basic,
    normalize_price_limits,
    normalize_security_master,
    normalize_suspension_events,
)
from astramind_mini.data.application.publication_policy import completed_session_cutoff
from astramind_mini.data.contracts import SecurityMasterObservation
from astramind_mini.data.ports import ProviderTable

RECEIVED_AT = datetime(2026, 1, 16, 10, tzinfo=UTC)


def table(api_name: str, rows: tuple[dict[str, object], ...]) -> ProviderTable:
    return ProviderTable(
        api_name=api_name,
        fields=tuple(rows[0]) if rows else (),
        rows=rows,
        raw_body={"code": 0, "data": {"items": rows}},
        request_identity="sha256:" + "1" * 64,
        received_at=RECEIVED_AT,
        source_endpoint="api.tushare.pro",
    )


def test_security_master_is_strict_and_records_conservative_availability() -> None:
    source = table(
        "stock_basic",
        (
            {
                "ts_code": "000001.SZ",
                "symbol": "000001",
                "name": "合成证券",
                "area": "深圳",
                "industry": "合成行业",
                "market": "主板",
                "exchange": "SZSE",
                "curr_type": "CNY",
                "list_status": "L",
                "list_date": "19910403",
                "delist_date": None,
                "is_hs": "S",
            },
        ),
    )

    observation = normalize_security_master((source,))[0]

    assert observation.available_at == RECEIVED_AT
    assert observation.retrieved_at == RECEIVED_AT
    with pytest.raises(ValidationError):
        SecurityMasterObservation.model_validate(
            {**observation.model_dump(), "unexpected": "blocked"}
        )


def test_normalization_fails_on_conflicts_invalid_ohlc_and_factors() -> None:
    security: dict[str, object] = {
        "ts_code": "000001.SZ",
        "symbol": "000001",
        "name": "合成证券",
        "exchange": "SZSE",
        "curr_type": "CNY",
        "list_status": "L",
    }
    changed = {**security, "name": "冲突名称"}
    with pytest.raises(ValueError, match="主键冲突"):
        normalize_security_master(
            (table("stock_basic", (security,)), table("stock_basic", (changed,)))
        )

    bad_bar = {
        "ts_code": "000001.SZ",
        "trade_date": "20260115",
        "open": 10,
        "high": 9,
        "low": 8,
        "close": 10,
        "pre_close": 9,
        "change": 1,
        "pct_chg": 11.11,
        "vol": 100,
        "amount": 1000,
    }
    with pytest.raises(ValueError, match="OHLC"):
        normalize_daily_bars(table("daily", (bad_bar,)))

    with pytest.raises(ValueError, match="必须为正数"):
        normalize_adjustment_factors(
            table(
                "adj_factor",
                (
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": "20260115",
                        "adj_factor": 0,
                    },
                ),
            )
        )


def test_completed_session_cutoff_uses_shanghai_1800_boundary() -> None:
    assert completed_session_cutoff(datetime(2026, 1, 16, 9, 59, tzinfo=UTC)).isoformat() == (
        "2026-01-15"
    )
    assert completed_session_cutoff(datetime(2026, 1, 16, 10, 0, tzinfo=UTC)).isoformat() == (
        "2026-01-16"
    )


def test_daily_metrics_limits_and_suspension_events_preserve_provider_semantics() -> None:
    metrics = normalize_daily_basic(
        table(
            "daily_basic",
            (
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260115",
                    "close": 10.0,
                    "turnover_rate": 1.2,
                    "turnover_rate_f": 1.5,
                    "pe": None,
                    "total_share": 100.0,
                    "total_mv": 1000.0,
                },
            ),
        )
    )
    limits = normalize_price_limits(
        table(
            "stk_limit",
            (
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260115",
                    "pre_close": None,
                    "up_limit": 0,
                    "down_limit": 0,
                },
            ),
        )
    )
    events = normalize_suspension_events(
        table(
            "suspend_d",
            (
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260115",
                    "suspend_timing": None,
                    "suspend_type": "S",
                },
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260115",
                    "suspend_timing": None,
                    "suspend_type": "R",
                },
            ),
        )
    )

    assert metrics[0].price_earnings is None
    assert metrics[0].total_market_value_ten_thousand_cny == 1000.0
    assert limits[0].limit_prices_usable is False
    assert [item.suspension_type for item in events] == ["R", "S"]
