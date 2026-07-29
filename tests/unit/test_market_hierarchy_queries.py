from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.market_regime.adapters.hierarchy_queries import (
    close_series,
    taxonomy_nodes,
)
from astramind_mini.market_regime.adapters.snapshot_hierarchy import (
    SnapshotIndustryHierarchy,
)
from astramind_mini.market_regime.adapters.stock_evidence_queries import (
    price_candles,
    stock_evidence,
)
from astramind_mini.market_regime.contracts import IndustryHierarchyNode, StockEvidence


def test_taxonomy_nodes_exclude_unpublished_provider_classifications(
    tmp_path: Path,
) -> None:
    taxonomy = tmp_path / "taxonomy.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT * FROM VALUES
                ('L2', '801081.SI', '半导体', '801080.SI', true),
                ('L2', '801089.SI', '停用分类', '801080.SI', false)
              t(level, industry_code, industry_name, parent_code, is_published)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(taxonomy)],
        )
        nodes = taxonomy_nodes(
            connection,
            [str(taxonomy)],
            level="L2",
            parent_code="801080.SI",
        )
    assert tuple(node.code for node in nodes) == ("801081.SI",)


def test_small_sibling_group_remains_navigable_without_inventing_rotation(
    tmp_path: Path,
) -> None:
    taxonomy = tmp_path / "taxonomy.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT * FROM VALUES
                ('L2', '801231.SI', '综合环境', '801230.SI', true),
                ('L2', '801232.SI', '综合服务', '801230.SI', true)
              t(level, industry_code, industry_name, parent_code, is_published)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(taxonomy)],
        )
        snapshot = DataSnapshot(
            snapshot_id="snapshot:sha256:" + "1" * 64,
            as_of=datetime(2026, 7, 28, tzinfo=UTC),
            datasets=(
                DatasetRef(
                    dataset_name="industry_taxonomy",
                    dataset_version="sha256:" + "2" * 64,
                    schema_version="1.0.0",
                    content_hash="sha256:" + "3" * 64,
                ),
            ),
            created_at=datetime(2026, 7, 28, tzinfo=UTC),
            code_identity="synthetic-hierarchy-test",
        )
        view = SnapshotIndustryHierarchy(tmp_path)._l2(
            connection,
            snapshot,
            {
                "industry_taxonomy": [str(taxonomy)],
                "industry_index_daily": [],
            },
            date(2026, 7, 27),
            "801230.SI",
            False,
        )
    assert view.status == "ready"
    assert len(view.nodes) == 2
    assert view.rotation is None
    assert "sibling_cross_section_below_three" in view.known_gaps


def test_stock_rotation_excludes_short_history_without_hiding_members(
    tmp_path: Path,
) -> None:
    daily = tmp_path / "daily.parquet"
    nodes = tuple(
        IndustryHierarchyNode(
            code=code,
            name=f"股票{index}",
            level="stock",
            parent_code="801081.SI",
        )
        for index, code in enumerate(
            ("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"),
            start=1,
        )
    )
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT code AS instrument_id,
                     DATE '2026-01-01' + CAST(day AS INTEGER) AS trade_date,
                     100.0 + day AS close
              FROM (VALUES
                ('000001.SZ', 141),
                ('000002.SZ', 141),
                ('000003.SZ', 141),
                ('000004.SZ', 20)
              ) instruments(code, sessions),
              range(141) days(day)
              WHERE day < sessions
            ) TO ? (FORMAT PARQUET)
            """,
            [str(daily)],
        )
        calendar, series, excluded = close_series(
            connection,
            [str(daily)],
            nodes,
            as_of=date(2026, 7, 27),
            stock=True,
            allow_incomplete=True,
        )
        with pytest.raises(ValueError, match="不足 141 日"):
            close_series(
                connection,
                [str(daily)],
                nodes,
                as_of=date(2026, 7, 27),
                stock=True,
            )

    assert len(calendar) == 141
    assert tuple(item.industry_code for item in series) == (
        "000001.SZ",
        "000002.SZ",
        "000003.SZ",
    )
    assert excluded == ("000004.SZ",)


def test_price_candles_only_publish_completed_week_and_month_periods(
    tmp_path: Path,
) -> None:
    market = tmp_path / "market.parquet"
    calendar = tmp_path / "calendar.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT '000001.SZ' instrument_id, CAST(day AS DATE) trade_date,
                     10.0 + row_number() OVER () AS "open",
                     11.0 + row_number() OVER () AS high,
                     9.0 + row_number() OVER () AS low,
                     10.5 + row_number() OVER () AS "close",
                     1000.0 volume_lots, 2000.0 amount_thousand_cny
              FROM generate_series(
                DATE '2026-06-01', DATE '2026-07-22', INTERVAL 1 DAY
              ) t(day)
              WHERE dayofweek(day) BETWEEN 1 AND 5
            ) TO ? (FORMAT PARQUET)
            """,
            [str(market)],
        )
        connection.execute(
            """
            COPY (
              SELECT 'SSE' exchange, CAST(day AS DATE) calendar_date, true is_open
              FROM generate_series(
                DATE '2026-06-01', DATE '2026-07-31', INTERVAL 1 DAY
              ) t(day)
              WHERE dayofweek(day) BETWEEN 1 AND 5
            ) TO ? (FORMAT PARQUET)
            """,
            [str(calendar)],
        )
        weekly = price_candles(
            connection,
            [str(market)],
            [str(calendar)],
            instrument_id="000001.SZ",
            as_of=date(2026, 7, 22),
            period="week",
        )
        monthly = price_candles(
            connection,
            [str(market)],
            [str(calendar)],
            instrument_id="000001.SZ",
            as_of=date(2026, 7, 22),
            period="month",
        )

    assert weekly[-1].trade_date == date(2026, 7, 17)
    assert monthly[-1].trade_date == date(2026, 6, 30)
    assert weekly[-1].amount_cny == 10_000_000


def test_stock_evidence_respects_availability_and_never_crosses_snapshot(
    tmp_path: Path,
) -> None:
    market = tmp_path / "market.parquet"
    basic = tmp_path / "basic.parquet"
    holders = tmp_path / "holders.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT * FROM VALUES
                ('000001.SZ', DATE '2026-07-19', 11.5, -0.01, 2500.0,
                 TIMESTAMPTZ '2026-07-19 18:00:00+08'),
                ('000001.SZ', DATE '2026-07-20', 12.0, 0.02, 3000.0,
                 TIMESTAMPTZ '2026-07-20 18:00:00+08')
              t(instrument_id, trade_date, close, percent_change,
                amount_thousand_cny, available_at)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(market)],
        )
        connection.execute(
            """
            COPY (
              SELECT * FROM VALUES
                ('000001.SZ', DATE '2026-07-19', 2.0, 17.0, 1.7,
                 90000.0, 70000.0, TIMESTAMPTZ '2026-07-19 18:00:00+08'),
                ('000001.SZ', DATE '2026-07-20', 2.5, 18.0, 1.8,
                 100000.0, 80000.0, TIMESTAMPTZ '2026-07-20 18:00:00+08')
              t(instrument_id, trade_date, turnover_rate, price_earnings_ttm,
                price_book, total_market_value_ten_thousand_cny,
                circulating_market_value_ten_thousand_cny, available_at)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(basic)],
        )
        connection.execute(
            """
            COPY (
              SELECT * FROM VALUES
                ('000001.SZ', DATE '2026-07-18', DATE '2026-06-30', 900,
                 TIMESTAMPTZ '2026-07-18 18:00:00+08'),
                ('000001.SZ', DATE '2026-04-18', DATE '2026-03-31', 1000,
                 TIMESTAMPTZ '2026-04-18 18:00:00+08'),
                ('000001.SZ', DATE '2026-08-18', DATE '2026-07-31', 700,
                 TIMESTAMPTZ '2026-08-18 18:00:00+08')
              t(instrument_id, announced_on, reporting_period, holder_count, available_at)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(holders)],
        )
        evidence = stock_evidence(
            connection,
            {
                "daily_market": [str(market)],
                "daily_basic": [str(basic)],
                "shareholder_count": [str(holders)],
            },
            instrument_id="000001.SZ",
            instrument_name="合成股票",
            as_of=date(2026, 7, 22),
        )
        without_holders = stock_evidence(
            connection,
            {"daily_market": [str(market)], "daily_basic": [str(basic)]},
            instrument_id="000001.SZ",
            instrument_name="合成股票",
            as_of=date(2026, 7, 22),
        )

    assert evidence.fundamental is not None
    assert evidence.fundamental.total_market_value_cny == 1_000_000_000
    assert_stock_evidence_history(evidence)
    assert without_holders.shareholder_concentration.status == "unavailable"
    assert "shareholder_count_not_in_snapshot" in without_holders.known_gaps


def assert_stock_evidence_history(evidence: StockEvidence) -> None:
    assert [item.market_date for item in evidence.fundamental_history] == [
        date(2026, 7, 19),
        date(2026, 7, 20),
    ]
    assert evidence.shareholder_concentration.holder_count == 900
    assert evidence.shareholder_concentration.change_rate == pytest.approx(-0.1)
    assert evidence.shareholder_concentration.direction == "concentrating"
    assert len(evidence.shareholder_concentration_history) == 2
    assert evidence.shareholder_concentration_history[0].status == "insufficient_history"
    assert evidence.shareholder_concentration_history[1].status == "ready"
