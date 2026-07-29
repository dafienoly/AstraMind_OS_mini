from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from astramind_mini.data.application.broad_index_normalization import (
    BROAD_INDEX_REGISTRY,
    normalize_broad_index_daily,
)
from astramind_mini.data.ports import ProviderTable
from astramind_mini.market_regime.adapters.dashboard_heat import industry_heat
from astramind_mini.market_regime.adapters.dashboard_queries import (
    index_views,
    market_totals,
)
from astramind_mini.market_regime.domain.dashboard import describe_regime


def test_broad_index_normalization_freezes_registry_and_cny_units() -> None:
    table = ProviderTable(
        api_name="index_daily",
        fields=(),
        rows=(
            {
                "ts_code": "000300.SH",
                "trade_date": "20260728",
                "open": 4500,
                "high": 4550,
                "low": 4480,
                "close": 4530,
                "pre_close": 4490,
                "change": 40,
                "pct_chg": 0.8909,
                "vol": 123_000,
                "amount": 456_000,
            },
        ),
        raw_body={},
        request_identity="sha256:" + "1" * 64,
        received_at=datetime(2026, 7, 28, 18, tzinfo=UTC),
        source_endpoint="fixture",
    )

    row = normalize_broad_index_daily(table)[0]

    assert row.instrument_name == "沪深300"
    assert row.amount_cny == 456_000_000
    assert row.available_at.isoformat().endswith("+08:00")


def test_market_dashboard_queries_use_one_cutoff_and_real_components(
    tmp_path: Path,
) -> None:
    paths = _write_projection_fixture(tmp_path)
    cutoff = date(2026, 7, 28)

    with duckdb.connect(":memory:") as connection:
        indexes = index_views(connection, paths["broad_index_daily"], cutoff)
        breadth, liquidity = market_totals(connection, paths, cutoff)
        heat = industry_heat(connection, paths, cutoff)

    assert tuple(item.instrument_id for item in indexes) == tuple(BROAD_INDEX_REGISTRY)
    assert all(item.latest_trade_date == cutoff for item in indexes)
    assert indexes[4].return_20d is not None
    assert breadth.advancing == 62
    assert breadth.declining == 31
    assert breadth.upper_limit_locked == 1
    assert liquidity.amount_cny > 0
    assert len(heat) == 31
    assert heat[0].relative_strength > heat[-1].relative_strength
    assert all(item.coverage_ratio == 1 for item in heat)
    assert heat[0].leading_instrument_name is not None

    regime = describe_regime(
        index_return_20d=indexes[4].return_20d,
        advance_ratio=breadth.advance_ratio,
        amount_change_20d=liquidity.amount_change_20d,
    )
    assert regime.state in {"strong", "balanced", "divergent"}
    assert regime.definition_version == "market-regime-breadth-price-v1.0.0"


def _write_projection_fixture(root: Path) -> dict[str, tuple[Path, ...]]:
    paths = {
        name: root / f"{name}.parquet"
        for name in (
            "broad_index_daily",
            "daily_market",
            "daily_tradability",
            "industry_index_daily",
            "industry_membership",
        )
    }
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              WITH sessions AS (
                SELECT CAST(day AS DATE) trade_date,
                       row_number() OVER (ORDER BY day) n
                FROM generate_series(
                  DATE '2024-07-01', DATE '2026-07-28', INTERVAL 1 DAY
                ) t(day) WHERE dayofweek(day) BETWEEN 1 AND 5
              ), registry AS (
                SELECT * FROM VALUES
                  ('000001.SH', '上证指数'), ('399001.SZ', '深证成指'),
                  ('399006.SZ', '创业板指'), ('000688.SH', '科创50'),
                  ('000300.SH', '沪深300'), ('000852.SH', '中证1000')
                r(instrument_id, instrument_name)
              )
              SELECT instrument_id, instrument_name, trade_date,
                     3000.0 + n AS open, 3010.0 + n AS high,
                     2990.0 + n AS low, 3005.0 + n AS close,
                     5.0 AS change, 0.1 AS percent_change,
                     100000.0 + n AS volume_lots, 200000000.0 + n AS amount_cny
              FROM sessions CROSS JOIN registry
            ) TO ? (FORMAT PARQUET)
            """,
            [str(paths["broad_index_daily"])],
        )
        connection.execute(
            """
            COPY (
              WITH sessions AS (
                SELECT CAST(day AS DATE) trade_date
                FROM generate_series(
                  DATE '2025-07-01', DATE '2026-07-28', INTERVAL 1 DAY
                ) t(day) WHERE dayofweek(day) BETWEEN 1 AND 5
              ), stocks AS (
                SELECT printf('%06d.SZ', n) instrument_id, n
                FROM range(1, 94) t(n)
              )
              SELECT instrument_id, trade_date, 10.0 AS close,
                     CASE WHEN n % 3 = 0 THEN -1.0 ELSE 1.0 END percent_change,
                     1000.0 + n AS amount_thousand_cny
              FROM sessions CROSS JOIN stocks
            ) TO ? (FORMAT PARQUET)
            """,
            [str(paths["daily_market"])],
        )
        connection.execute(
            """
            COPY (
              SELECT printf('%06d.SZ', n) instrument_id, DATE '2026-07-28' trade_date,
                     n = 1 AS upper_limit_locked, n = 2 AS lower_limit_locked
              FROM range(1, 94) t(n)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(paths["daily_tradability"])],
        )
        connection.execute(
            """
            COPY (
              WITH sessions AS (
                SELECT CAST(day AS DATE) trade_date,
                       row_number() OVER (ORDER BY day) n
                FROM generate_series(
                  DATE '2026-06-01', DATE '2026-07-28', INTERVAL 1 DAY
                ) t(day) WHERE dayofweek(day) BETWEEN 1 AND 5
              ), industries AS (
                SELECT printf('801%03d.SI', i) industry_code,
                       printf('行业%02d', i) industry_name, i
                FROM range(1, 32) t(i)
              )
              SELECT 'L1' AS "level", industry_code, industry_name, trade_date,
                     CAST(i AS DOUBLE) / 10 AS percent_change,
                     100000.0 + i * n AS amount_provider_native,
                     20.0 + i AS price_earnings, 2.0 + i / 10 AS price_book
              FROM sessions CROSS JOIN industries
            ) TO ? (FORMAT PARQUET)
            """,
            [str(paths["industry_index_daily"])],
        )
        connection.execute(
            """
            COPY (
              SELECT 'L1' AS "level", printf('801%03d.SI', i) industry_code,
                     printf('%06d.SZ', (i - 1) * 3 + member) instrument_id,
                     printf('股票%03d', (i - 1) * 3 + member) instrument_name,
                     DATE '2020-01-01' effective_from, NULL::DATE effective_to,
                     TIMESTAMPTZ '2020-01-01 18:00:00+08' available_at,
                     TIMESTAMPTZ '2026-07-28 18:00:00+08' retrieved_at
              FROM range(1, 32) industries(i), range(1, 4) members(member)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(paths["industry_membership"])],
        )
    return {name: (path,) for name, path in paths.items()}
