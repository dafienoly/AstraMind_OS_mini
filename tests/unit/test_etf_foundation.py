from datetime import UTC, date, datetime, time, timedelta
from typing import TypedDict

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.etf_foundation.contracts import (
    EtfDailyObservation,
    EtfMasterObservation,
    EtfShareObservation,
)
from astramind_mini.data.etf_foundation.normalization import (
    mapping_observations,
    normalize_daily,
    normalize_master,
    normalize_share,
)
from astramind_mini.data.etf_foundation.qualification import qualify_etfs
from astramind_mini.data.etf_foundation.registry import (
    ETF_CODES,
    ETF_MAPPINGS,
    MAPPING_EFFECTIVE_FROM,
    validate_registry,
)
from astramind_mini.data.ports import ProviderTable

RECEIVED_AT = datetime(2026, 7, 29, 10, tzinfo=UTC)
CUTOFF = date(2026, 7, 29)


class SourceFields(TypedDict):
    provider: str
    source_endpoint: str
    retrieved_at: datetime
    available_at: datetime
    schema_version: str
    source_record_hash: str


def test_registry_covers_every_sw2021_l1_identity_without_silent_proxy_eligibility() -> None:
    validate_registry()

    identities = {(row.industry_code, row.industry_name) for row in ETF_MAPPINGS}
    assert len(identities) == 31
    assert all(row.eligible == (row.tier == "exact") for row in ETF_MAPPINGS)


def test_provider_units_and_availability_are_normalized_explicitly() -> None:
    master = normalize_master(
        _table(
            "fund_basic",
            tuple(
                {
                    "ts_code": code,
                    "name": f"合成ETF-{code}",
                    "list_date": "20200102",
                    "status": "L",
                }
                for code in ETF_CODES
            ),
        )
    )
    daily = normalize_daily(
        _table(
            "fund_daily",
            (
                {
                    "ts_code": ETF_CODES[0],
                    "trade_date": "20260729",
                    "open": 2.0,
                    "high": 2.1,
                    "low": 1.9,
                    "close": 2.0,
                    "pre_close": 1.98,
                    "change": 0.02,
                    "pct_chg": 1.01,
                    "vol": 1000,
                    "amount": 50_000,
                },
            ),
        )
    )
    shares = normalize_share(
        _table(
            "fund_share",
            (
                {
                    "ts_code": ETF_CODES[0],
                    "trade_date": "20260729",
                    "fd_share": 10_000,
                },
            ),
        )
    )

    assert len(master) == len(ETF_CODES)
    assert master[0].available_at == RECEIVED_AT
    assert daily[0].amount_cny == 50_000_000
    assert daily[0].available_at.hour == 18
    assert str(daily[0].available_at.tzinfo) == "Asia/Shanghai"
    assert shares[0].fund_share == 100_000_000
    assert shares[0].available_at == RECEIVED_AT


def test_qualification_is_point_in_time_and_never_opens_strategy_gate() -> None:
    exact_mapping = next(
        row
        for row in mapping_observations(RECEIVED_AT)
        if row.semantic_tier == "exact" and row.etf_code is not None
    )
    code = exact_mapping.etf_code
    assert code is not None
    masters = (_master(code),)
    daily = tuple(_daily(code, CUTOFF - timedelta(days=251 - offset)) for offset in range(252))
    shares = (
        _share(code, CUTOFF, 100_000_000),
        _share(code, CUTOFF + timedelta(days=1), 1.0),
    )

    result = qualify_etfs(
        data_snapshot_id=content_hash("snapshot"),
        cutoff=CUTOFF,
        masters=masters,
        daily=daily,
        shares=shares,
        mappings=(exact_mapping,),
    )

    assert result[0].state == "foundation_eligible"
    assert result[0].latest_size_cny == 200_000_000
    assert result[0].strategy_gate_ready is False
    assert "spread_not_measured" in result[0].known_gaps


def test_mapping_is_not_backdated_and_proxy_stays_context_only() -> None:
    mappings = mapping_observations(RECEIVED_AT)
    exact_mapping = next(row for row in mappings if row.semantic_tier == "exact")
    proxy_mapping = next(row for row in mappings if row.semantic_tier == "composite_proxy")

    historical = qualify_etfs(
        data_snapshot_id=content_hash("historical"),
        cutoff=MAPPING_EFFECTIVE_FROM - timedelta(days=1),
        masters=(),
        daily=(),
        shares=(),
        mappings=(exact_mapping,),
    )
    proxy = qualify_etfs(
        data_snapshot_id=content_hash("proxy"),
        cutoff=CUTOFF,
        masters=(),
        daily=(),
        shares=(),
        mappings=(proxy_mapping,),
    )

    assert historical[0].state == "unavailable"
    assert historical[0].known_gaps == ("mapping_not_effective_at_cutoff",)
    assert proxy[0].state == "context_only"
    assert proxy[0].strategy_gate_ready is False


def test_liquidity_threshold_fails_closed() -> None:
    mapping = next(
        row
        for row in mapping_observations(RECEIVED_AT)
        if row.semantic_tier == "exact" and row.etf_code is not None
    )
    code = mapping.etf_code
    assert code is not None
    daily = tuple(
        _daily(code, CUTOFF - timedelta(days=251 - offset), amount=19_999_999)
        for offset in range(252)
    )

    result = qualify_etfs(
        data_snapshot_id=content_hash("illiquid"),
        cutoff=CUTOFF,
        masters=(_master(code),),
        daily=daily,
        shares=(_share(code, CUTOFF, 100_000_000),),
        mappings=(mapping,),
    )

    assert result[0].state == "insufficient_liquidity"
    assert "median_amount_20d_below_20m" in result[0].known_gaps


def _table(api_name: str, rows: tuple[dict[str, object], ...]) -> ProviderTable:
    return ProviderTable(
        api_name=api_name,
        fields=tuple(rows[0]) if rows else (),
        rows=rows,
        raw_body={"api_name": api_name, "rows": rows},
        request_identity=content_hash({"api_name": api_name, "rows": rows}),
        received_at=RECEIVED_AT,
        source_endpoint="synthetic.tushare.local",
    )


def _source(day: date) -> SourceFields:
    observed = datetime.combine(day, time(18), tzinfo=UTC)
    return {
        "provider": "synthetic",
        "source_endpoint": "fixture",
        "retrieved_at": RECEIVED_AT,
        "available_at": observed,
        "schema_version": "1.0.0",
        "source_record_hash": content_hash({"day": day}),
    }


def _master(code: str) -> EtfMasterObservation:
    return EtfMasterObservation(
        **_source(date(2020, 1, 2)),
        instrument_id=code,
        name="合成ETF",
        exchange="SSE" if code.endswith(".SH") else "SZSE",
        list_date=date(2020, 1, 2),
        list_status="L",
    )


def _daily(
    code: str,
    day: date,
    *,
    amount: float = 50_000_000,
) -> EtfDailyObservation:
    return EtfDailyObservation(
        **_source(day),
        instrument_id=code,
        trade_date=day,
        open=2.0,
        high=2.1,
        low=1.9,
        close=2.0,
        previous_close=2.0,
        change=0,
        percent_change=0,
        volume_lots=1_000_000,
        amount_cny=amount,
    )


def _share(code: str, day: date, shares: float) -> EtfShareObservation:
    return EtfShareObservation(
        **_source(day),
        instrument_id=code,
        trade_date=day,
        fund_share=shares,
    )
