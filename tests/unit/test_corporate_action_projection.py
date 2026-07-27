from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from astramind_mini.data.adapters import DuckDBCorporateActionProjector


def _parquet(path: Path, query: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(path).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET)")
    return path


def _action_source(path: Path) -> Path:
    return _parquet(
        path,
        """
        SELECT '000001.SZ' ts_code, DATE '2019-12-31' end_date,
               DATE '2020-01-01' ann_date, '实施' div_proc,
               0.1 stk_div, 0.2 cash_div, 0.18 cash_div_tax,
               DATE '2020-01-01' record_date, DATE '2020-01-03' ex_date,
               DATE '2020-01-04' pay_date, DATE '2020-01-01' base_date,
               100.0 base_share, repeat('a', 64) record_hash,
               repeat('b', 64) _raw_sha256
        UNION ALL
        SELECT '000002.SZ', DATE '2019-12-31', NULL::DATE, '预案',
               NULL::DOUBLE, NULL::DOUBLE, NULL::DOUBLE,
               NULL::DATE, NULL::DATE, NULL::DATE, NULL::DATE,
               NULL::DOUBLE, repeat('c', 64), repeat('d', 64)
        """,
    )


def test_company_actions_preserve_unknown_availability(tmp_path: Path) -> None:
    output = tmp_path / "actions.parquet"
    stats = DuckDBCorporateActionProjector().compact_actions(
        source_files=(_action_source(tmp_path / "source.parquet"),),
        output=output,
        imported_at=datetime(2026, 7, 27, tzinfo=UTC),
    )

    with duckdb.connect(":memory:") as connection:
        rows = connection.execute(
            """
            SELECT action_kind, availability_known, is_implemented
            FROM read_parquet(?) ORDER BY instrument_id
            """,
            [str(output)],
        ).fetchall()
    assert rows == [
        ("cash_and_stock", True, True),
        ("unspecified", False, False),
    ]
    assert stats["rows"] == stats["unique_records"] == 2
    assert stats["unknown_availability_rows"] == 1


def test_adjusted_prices_are_explicit_and_index_continues_across_years(
    tmp_path: Path,
) -> None:
    projector = DuckDBCorporateActionProjector()
    actions = tmp_path / "actions.parquet"
    projector.compact_actions(
        source_files=(_action_source(tmp_path / "source.parquet"),),
        output=actions,
        imported_at=datetime(2026, 7, 27, tzinfo=UTC),
    )
    factors_2020 = _parquet(
        tmp_path / "factor-2020.parquet",
        """
        SELECT '000001.SZ' instrument_id, DATE '2020-01-02' trade_date,
               1.0 adjustment_factor
        UNION ALL SELECT '000001.SZ', DATE '2020-01-03', 2.0
        """,
    )
    factors_2021 = _parquet(
        tmp_path / "factor-2021.parquet",
        """
        SELECT '000002.SZ' instrument_id, DATE '2021-01-04' trade_date,
               1.0 adjustment_factor
        """,
    )
    factors_2022 = _parquet(
        tmp_path / "factor-2022.parquet",
        """
        SELECT '000001.SZ' instrument_id, DATE '2022-01-04' trade_date,
               2.0 adjustment_factor
        """,
    )
    factor_anchors = tmp_path / "factor-anchors.parquet"
    projector.build_factor_anchors(
        factor_files=(factors_2020, factors_2021, factors_2022),
        output=factor_anchors,
    )
    daily_2020 = _parquet(
        tmp_path / "daily-2020.parquet",
        """
        SELECT '000001.SZ' instrument_id, DATE '2020-01-02' trade_date,
               9.0 AS "open", 11.0 high, 8.0 low, 10.0 AS "close",
               0.0 percent_change
        UNION ALL SELECT '000001.SZ', DATE '2020-01-03',
               5.5, 6.5, 5.0, 6.0, 10.0
        """,
    )
    daily_2021 = _parquet(
        tmp_path / "daily-2021.parquet",
        """
        SELECT '000002.SZ' instrument_id, DATE '2021-01-04' trade_date,
               4.8 AS "open", 5.2 high, 4.5 low, 5.0 AS "close",
               0.0 percent_change
        """,
    )
    daily_2022 = _parquet(
        tmp_path / "daily-2022.parquet",
        """
        SELECT '000001.SZ' instrument_id, DATE '2022-01-04' trade_date,
               6.8 AS "open", 7.2 high, 6.5 low, 7.0 AS "close",
               5.0 percent_change
        """,
    )
    out_2020 = tmp_path / "adjusted-2020.parquet"
    anchor_2020 = tmp_path / "anchor-2020.parquet"
    stats = projector.project_year(
        daily_files=(daily_2020,),
        factor_files=(factors_2020,),
        action_history=actions,
        factor_anchors=factor_anchors,
        previous_index_anchors=None,
        output=out_2020,
        next_index_anchors=anchor_2020,
        imported_at=datetime(2026, 7, 27, tzinfo=UTC),
    )
    out_2021 = tmp_path / "adjusted-2021.parquet"
    projector.project_year(
        daily_files=(daily_2021,),
        factor_files=(factors_2021,),
        action_history=actions,
        factor_anchors=factor_anchors,
        previous_index_anchors=anchor_2020,
        output=out_2021,
        next_index_anchors=tmp_path / "anchor-2021.parquet",
        imported_at=datetime(2026, 7, 27, tzinfo=UTC),
    )
    out_2022 = tmp_path / "adjusted-2022.parquet"
    projector.project_year(
        daily_files=(daily_2022,),
        factor_files=(factors_2022,),
        action_history=actions,
        factor_anchors=factor_anchors,
        previous_index_anchors=tmp_path / "anchor-2021.parquet",
        output=out_2022,
        next_index_anchors=tmp_path / "anchor-2022.parquet",
        imported_at=datetime(2026, 7, 27, tzinfo=UTC),
    )

    with duckdb.connect(":memory:") as connection:
        row_2020 = connection.execute(
            """
            SELECT forward_adjusted_close, backward_adjusted_close,
                   research_close_index, factor_changed,
                   has_implemented_action_evidence
            FROM read_parquet(?) ORDER BY trade_date DESC LIMIT 1
            """,
            [str(out_2020)],
        ).fetchone()
        row_2022 = connection.execute(
            "SELECT research_close_index FROM read_parquet(?)",
            [str(out_2022)],
        ).fetchone()
    assert row_2020 is not None and row_2022 is not None
    assert row_2020[:3] == pytest.approx((6.0, 12.0, 1.1))
    assert row_2020[3:] == (True, True)
    assert row_2022[0] == pytest.approx(1.155)
    assert stats["rows"] == stats["unique_rows"] == 2
    assert stats["factor_changes_with_action"] == 1
