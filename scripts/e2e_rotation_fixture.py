"""Create one cohesive synthetic market fixture for cross-page browser acceptance.

The fixture intentionally stays in one module so rotation, hierarchy, dashboard, and
daily-status browser flows share exactly one snapshot identity.
"""

import json
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import duckdb

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.data.adapters import DailyPipelineStore
from astramind_mini.data.contracts import DailyPipelineStatus
from astramind_mini.local_ops.contracts import DailyDecisionStatus
from astramind_mini.local_ops.daily_decision_store import DailyDecisionStore
from astramind_mini.market_regime.contracts import MarketRotationSnapshot
from astramind_mini.market_regime.domain.rotation import (
    IndustryCloseSeries,
    build_rotation_snapshot,
)
from astramind_mini.market_regime.public import FilesystemRotationStore, production_formula


def prepare(root: Path) -> MarketRotationSnapshot:
    calendar = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(141))
    industries = tuple(
        IndustryCloseSeries(
            industry_code=f"8010{index}0.SI",
            industry_name=f"合成行业{label}",
            closes={
                day: 100 * (1 + slope) ** offset * (1 + wave * ((offset + index) % 7))
                for offset, day in enumerate(calendar)
            },
            constituent_counts={day: 8 + index for day in calendar},
        )
        for index, (label, slope, wave) in enumerate(
            (
                ("甲", 0.0015, 0.0007),
                ("乙", 0.0004, -0.0005),
                ("丙", -0.0008, 0.0002),
                ("丁", -0.0002, -0.0006),
            ),
            start=1,
        )
    )
    snapshot = build_rotation_snapshot(
        data_snapshot_id="snapshot:sha256:" + "e" * 64,
        as_of=datetime(2025, 5, 21, tzinfo=UTC),
        created_at=datetime(2025, 5, 21, tzinfo=UTC),
        calendar=calendar,
        industries=industries,
        formula=production_formula(),
        known_gaps=("synthetic_e2e_fixture",),
    )
    FilesystemRotationStore(root).publish(snapshot)
    return snapshot


def _write_hierarchy_datasets(root: Path) -> tuple[DatasetRef, ...]:
    return (
        _write_dataset(
            root,
            "trade_calendar",
            """
            SELECT 'SSE' exchange, CAST(day AS DATE) calendar_date, true is_open
            FROM generate_series(
              DATE '2012-01-02', DATE '2025-05-30', INTERVAL 1 DAY
            ) t(day)
            WHERE dayofweek(day) BETWEEN 1 AND 5
            """,
        ),
        _write_dataset(
            root,
            "industry_taxonomy",
            """
            SELECT 'SYNTH' taxonomy, 'SYNTH-HIER' taxonomy_version,
                   'L1' "level", printf('8010%d0.SI', l1) industry_code,
                   printf('合成行业%d', l1) industry_name,
                   CAST(NULL AS VARCHAR) parent_code, true is_published
            FROM range(1, 5) t(l1)
            UNION ALL
            SELECT 'SYNTH', 'SYNTH-HIER', 'L2', printf('8010%d%d.SI', l1, l2),
                   printf('合成二级%d-%d', l1, l2),
                   printf('8010%d0.SI', l1), true
            FROM range(1, 5) a(l1), range(1, 4) b(l2)
            UNION ALL
            SELECT 'SW', 'SW2021', 'L1', printf('801%03d.SI', l1),
                   printf('合成一级行业%02d', l1), CAST(NULL AS VARCHAR), true
            FROM range(1, 32) t(l1)
            """,
        ),
        _write_dataset(
            root,
            "industry_index_daily",
            """
            WITH sessions AS (
              SELECT CAST(day AS DATE) trade_date,
                     row_number() OVER (ORDER BY day) session_no
              FROM generate_series(
                DATE '2012-01-02', DATE '2025-05-21', INTERVAL 1 DAY
              ) t(day)
              WHERE dayofweek(day) BETWEEN 1 AND 5
            )
            SELECT 'L2' "level", printf('8010%d%d.SI', l1, l2) industry_code,
                   printf('合成二级%d-%d', l1, l2) industry_name,
                   trade_date,
                   80 + l1 * 7 + l2 * 3 + session_no * (0.012 + l2 * 0.002)
                     + sin(session_no / (9.0 + l1)) "close",
                   CAST(NULL AS DOUBLE) percent_change,
                   CAST(NULL AS DOUBLE) amount_provider_native,
                   CAST(NULL AS DOUBLE) price_earnings,
                   CAST(NULL AS DOUBLE) price_book
            FROM range(1, 5) a(l1), range(1, 4) b(l2), sessions
            UNION ALL
            SELECT 'L1', printf('801%03d.SI', l1),
                   printf('合成一级行业%02d', l1), trade_date,
                   100 + l1 * 2 + session_no * (0.01 + l1 * 0.0004),
                   -1.6 + l1 * 0.1,
                   100000 + l1 * 5000 + session_no * 20,
                   12 + l1 * 0.5,
                   1 + l1 * 0.04
            FROM range(1, 32) a(l1), sessions
            """,
        ),
        _write_dataset(
            root,
            "security_master",
            """
            SELECT printf('60%04d.SH', stock_id) instrument_id,
                   printf('合成股票%02d', stock_id) "name",
                   'SH' exchange,
                   '主板' market
            FROM range(1, 37) t(stock_id)
            """,
        ),
        _write_dataset(
            root,
            "security_name_history",
            """
            SELECT printf('60%04d.SH', stock_id) instrument_id,
                   printf('合成股票%02d', stock_id) "name",
                   'normal' risk_status,
                   false is_special_treatment,
                   DATE '2012-01-01' effective_start_date,
                   CAST(NULL AS DATE) effective_end_date,
                   TIMESTAMPTZ '2012-01-01 18:00:00+08' available_at
            FROM range(1, 37) t(stock_id)
            """,
        ),
        _write_dataset(
            root,
            "industry_membership",
            """
            SELECT 'SYNTH' taxonomy, 'SYNTH-HIER' taxonomy_version,
                   printf('60%04d.SH', stock_id) instrument_id,
                   printf('合成股票%02d', stock_id) instrument_name,
                   'L2' "level", printf('8010%d%d.SI', l1, l2) industry_code,
                   printf('合成二级%d-%d', l1, l2) industry_name,
                   DATE '2012-01-01' effective_from,
                   CAST(NULL AS DATE) effective_to,
                   TIMESTAMPTZ '2012-01-01 18:00:00+08' available_at,
                   TIMESTAMPTZ '2025-05-21 18:00:00+08' retrieved_at
            FROM range(1, 5) a(l1), range(1, 4) b(l2), range(1, 4) c(member),
            LATERAL (
              SELECT CAST((l1 - 1) * 9 + (l2 - 1) * 3 + member AS INTEGER) stock_id
            )
            UNION ALL
            SELECT 'SW', 'SW2021', printf('60%04d.SH', l1),
                   printf('合成股票%02d', l1),
                   'L1', printf('801%03d.SI', l1),
                   printf('合成一级行业%02d', l1), DATE '2012-01-01',
                   CAST(NULL AS DATE), TIMESTAMPTZ '2012-01-01 18:00:00+08',
                   TIMESTAMPTZ '2025-05-21 18:00:00+08'
            FROM range(1, 32) t(l1)
            """,
        ),
    )


def _write_stock_datasets(root: Path) -> tuple[DatasetRef, ...]:
    return (
        _write_dataset(
            root,
            "broad_index_daily",
            """
            WITH sessions AS (
              SELECT CAST(day AS DATE) trade_date,
                     row_number() OVER (ORDER BY day) session_no
              FROM generate_series(
                DATE '2023-01-02', DATE '2025-05-21', INTERVAL 1 DAY
              ) t(day)
              WHERE dayofweek(day) BETWEEN 1 AND 5
            ), indexes AS (
              SELECT * FROM (VALUES
                ('000001.SH', '上证指数', 3200.0),
                ('399001.SZ', '深证成指', 10500.0),
                ('399006.SZ', '创业板指', 2100.0),
                ('000688.SH', '科创50', 980.0),
                ('000300.SH', '沪深300', 3900.0),
                ('000852.SH', '中证1000', 6100.0)
              ) t(instrument_id, instrument_name, base)
            ), bars AS (
              SELECT *, base + session_no * 0.8
                + sin(session_no / 11.0) * base * 0.004 AS close
              FROM sessions CROSS JOIN indexes
            )
            SELECT instrument_id, instrument_name, trade_date,
                   close - 4 "open", close + 8 high, close - 9 low, close,
                   4.0 change, 0.12 percent_change,
                   800000 + session_no * 900 volume_lots,
                   12000000000 + session_no * 1000000 amount_cny
            FROM bars
            """,
        ),
        _write_dataset(
            root,
            "daily_market",
            """
            WITH sessions AS (
              SELECT CAST(day AS DATE) trade_date,
                     row_number() OVER (ORDER BY day) session_no
              FROM generate_series(
                DATE '2012-01-02', DATE '2025-05-21', INTERVAL 1 DAY
              ) t(day)
              WHERE dayofweek(day) BETWEEN 1 AND 5
            ), bars AS (
              SELECT stock_id, trade_date, session_no,
                     8 + stock_id * 0.3 + session_no * (0.004 + stock_id * 0.00003)
                       + sin(session_no / (10.0 + stock_id % 5)) * 0.18 base
              FROM range(1, 37) t(stock_id), sessions
            )
            SELECT printf('60%04d.SH', stock_id) instrument_id, trade_date,
                   base - 0.03 "open", base + 0.12 high, base - 0.14 low,
                   base "close",
                   30000 + stock_id * 1200 + session_no * 7 volume_lots,
                   (30000 + stock_id * 1200 + session_no * 7) * base / 10
                     amount_thousand_cny,
                   CASE WHEN session_no = 1 THEN 0.0 ELSE 0.0008 + stock_id * 0.00001 END
                     percent_change,
                   CAST(trade_date AS TIMESTAMPTZ) + INTERVAL 16 HOUR available_at
            FROM bars
            """,
        ),
        _write_dataset(
            root,
            "daily_tradability",
            """
            SELECT printf('60%04d.SH', stock_id) instrument_id,
                   DATE '2025-05-21' trade_date,
                   stock_id IN (1, 2) upper_limit_locked,
                   stock_id = 36 lower_limit_locked,
                   'eligible' research_eligibility,
                   true has_daily_bar
            FROM range(1, 37) t(stock_id)
            """,
        ),
        _write_dataset(
            root,
            "daily_basic",
            """
            SELECT printf('60%04d.SH', stock_id) instrument_id,
                   trade_date,
                   1.2 + stock_id * 0.04 turnover_rate,
                   14.0 + stock_id * 0.8 price_earnings_ttm,
                   1.1 + stock_id * 0.06 price_book,
                   0.012 + stock_id * 0.0001 dividend_yield_ttm,
                   70000.0 + stock_id * 2500 total_market_value_ten_thousand_cny,
                   52000.0 + stock_id * 1900 circulating_market_value_ten_thousand_cny,
                   CAST(trade_date AS TIMESTAMPTZ) + INTERVAL 18 HOUR available_at
            FROM range(1, 37) t(stock_id),
            (VALUES (DATE '2025-05-20'), (DATE '2025-05-21')) dates(trade_date)
            """,
        ),
        _write_dataset(
            root,
            "shareholder_count",
            """
            SELECT printf('60%04d.SH', stock_id) instrument_id, announced_on,
                   reporting_period,
                   CAST(12500 - stock_id * 25 + period * 600 AS BIGINT) holder_count,
                   CAST(announced_on AS TIMESTAMPTZ) + INTERVAL 18 HOUR available_at
            FROM range(1, 37) t(stock_id),
            (VALUES
              (DATE '2025-04-18', DATE '2025-03-31', 0),
              (DATE '2025-01-20', DATE '2024-12-31', 1),
              (DATE '2024-10-20', DATE '2024-09-30', 2)
            ) periods(announced_on, reporting_period, period)
            """,
        ),
    )


def _write_lifecycle_datasets(root: Path) -> tuple[DatasetRef, ...]:
    return (
        _write_dataset(
            root,
            "adjusted_market",
            """
            WITH sessions AS (
              SELECT CAST(day AS DATE) trade_date,
                     row_number() OVER (ORDER BY day) session_no
              FROM generate_series(
                DATE '2024-01-02', DATE '2025-05-21', INTERVAL 1 DAY
              ) t(day)
              WHERE dayofweek(day) BETWEEN 1 AND 5
            ), values AS (
              SELECT printf('60%04d.SH', stock_id) instrument_id, trade_date,
                     100 * exp(
                     session_no * (0.0004 + stock_id * 0.00001)
                     + 0.018 * sin((session_no + stock_id * 2) / 9.0)
                     ) research_close_index
              FROM range(1, 37) t(stock_id), sessions
            )
            SELECT *, research_close_index
              / lag(research_close_index) OVER (
                PARTITION BY instrument_id ORDER BY trade_date
              ) - 1 reported_total_return
            FROM values
            """,
        ),
    )


def _write_fixture_datasets(root: Path) -> tuple[DatasetRef, ...]:
    return (
        _write_hierarchy_datasets(root)
        + _write_stock_datasets(root)
        + _write_lifecycle_datasets(root)
    )


def prepare_data_snapshot(root: Path) -> DataSnapshot:
    snapshot = DataSnapshot(
        snapshot_id="snapshot:sha256:" + "e" * 64,
        as_of=datetime(2025, 5, 21, tzinfo=UTC),
        datasets=_write_fixture_datasets(root),
        created_at=datetime(2025, 5, 21, tzinfo=UTC),
        code_identity="synthetic-e2e-hierarchy",
        known_gaps=("synthetic_e2e_fixture",),
    )
    target = root / "snapshots" / ("e" * 64)
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
    current = root / "current"
    current.mkdir(parents=True, exist_ok=True)
    (current / "data-snapshot.json").write_text(
        json.dumps({"snapshot_id": snapshot.snapshot_id}),
        encoding="utf-8",
    )
    return snapshot


def _write_dataset(root: Path, name: str, query: str) -> DatasetRef:
    digest = sha256(f"wp-0033:{name}:v1".encode()).hexdigest()
    dataset = root / "datasets" / name / digest
    dataset.mkdir(parents=True, exist_ok=True)
    artifact = dataset / "data.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"COPY ({query}) TO ? (FORMAT PARQUET)", [str(artifact)])
    content_hash = sha256(artifact.read_bytes()).hexdigest()
    (dataset / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_version": "sha256:" + digest,
                "content_hash": "sha256:" + content_hash,
                "artifact_paths": [artifact.name],
                "provider": "synthetic-e2e",
            }
        ),
        encoding="utf-8",
    )
    return DatasetRef(
        dataset_name=name,
        dataset_version="sha256:" + digest,
        schema_version="1.0.0",
        content_hash="sha256:" + content_hash,
    )


def prepare_daily_statuses(
    *,
    data_root: Path,
    control_db: Path,
    local_ops_db: Path,
    decision_root: Path,
) -> None:
    recorded_at = datetime(2025, 5, 21, 18, tzinfo=UTC)
    DailyPipelineStore(control_db, data_root).publish_status(
        DailyPipelineStatus(
            run_id="daily-pipeline:synthetic-e2e",
            target_date=date(2025, 5, 21),
            base_snapshot_id="snapshot:sha256:" + "a" * 64,
            state="current",
            attempt=1,
            expected_l1_count=31,
            expected_l2_count=124,
            observed_l1_count=31,
            observed_l2_count=124,
            data_snapshot_id="snapshot:sha256:" + "e" * 64,
            rotation_snapshot_id="rotation:sha256:" + "f" * 64,
            started_at=recorded_at,
            updated_at=recorded_at,
            completed_at=recorded_at,
            content_hash="sha256:" + "1" * 64,
        )
    )
    DailyDecisionStore(local_ops_db, decision_root).publish_status(
        DailyDecisionStatus(
            run_id="daily-decision:synthetic-e2e",
            pipeline_commit_id="daily-pipeline-commit:synthetic-e2e",
            signal_date=date(2025, 5, 21),
            state="current",
            feature_snapshot_id="feature-snapshot:" + "2" * 64,
            prediction_batch_id="prediction-batch:" + "3" * 64,
            portfolio_target_id="portfolio-target:" + "4" * 64,
            order_plan_id="order-plan:" + "5" * 64,
            shadow_preflight_state="ready",
            paper_preflight_state="ready",
            started_at=recorded_at,
            updated_at=recorded_at,
            completed_at=recorded_at,
            content_hash="sha256:" + "6" * 64,
        )
    )


__all__ = ["prepare", "prepare_daily_statuses", "prepare_data_snapshot"]
