from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from astramind_mini.data.adapters import DuckDBHistoricalStatusProjector


def _parquet(path: Path, query: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(path).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET)")
    return path


def test_name_intervals_are_closed_and_risk_is_classified(tmp_path: Path) -> None:
    source = _parquet(
        tmp_path / "namechange.parquet",
        """
        SELECT '000001.SZ' ts_code, '*ST示例' AS "name", DATE '2019-01-01' start_date,
               NULL::DATE end_date, DATE '2019-01-01' ann_date, '*ST' change_reason,
               repeat('a', 64) _raw_sha256
        UNION ALL
        SELECT '000001.SZ', '示例股份', DATE '2020-01-03', NULL::DATE,
               DATE '2020-01-03', '撤销*ST', repeat('b', 64)
        UNION ALL
        SELECT '000002.SZ', '退市示例', DATE '2020-01-01', NULL::DATE,
               DATE '2020-01-01', '退市整理期', repeat('c', 64)
        """,
    )
    output = tmp_path / "names.parquet"
    stats = DuckDBHistoricalStatusProjector().compact_name_history(
        source_files=(source,),
        output=output,
        imported_at=datetime(2026, 7, 27, tzinfo=UTC),
    )

    with duckdb.connect(":memory:") as connection:
        rows = connection.execute(
            """
            SELECT name, effective_end_date, risk_status, is_special_treatment
            FROM read_parquet(?) ORDER BY instrument_id, effective_start_date
            """,
            [str(output)],
        ).fetchall()
    assert rows == [
        ("*ST示例", date(2020, 1, 2), "star_st", True),
        ("示例股份", None, "normal", False),
        ("退市示例", None, "high_risk", True),
    ]
    assert stats["adjusted_intervals"] == 1
    assert stats["special_treatment_rows"] == 2


def test_daily_projection_fails_closed_for_unknown_evidence(tmp_path: Path) -> None:
    source = _parquet(
        tmp_path / "namechange.parquet",
        """
        SELECT '000001.SZ' ts_code, '*ST示例' AS "name", DATE '2019-01-01' start_date,
               NULL::DATE end_date, DATE '2019-01-01' ann_date, '*ST' change_reason,
               repeat('a', 64) _raw_sha256
        """,
    )
    projector = DuckDBHistoricalStatusProjector()
    names = tmp_path / "names.parquet"
    projector.compact_name_history(
        source_files=(source,),
        output=names,
        imported_at=datetime(2026, 7, 27, tzinfo=UTC),
    )
    securities = _parquet(
        tmp_path / "securities.parquet",
        """
        SELECT instrument_id, DATE '2019-01-01' list_date, NULL::DATE delist_date
        FROM (VALUES ('000001.SZ'), ('000002.SZ'), ('000003.SZ')) t(instrument_id)
        """,
    )
    calendar = _parquet(
        tmp_path / "calendar.parquet",
        """
        SELECT DATE '2020-01-02' calendar_date, true is_open
        UNION ALL SELECT DATE '2020-01-03', true
        """,
    )
    daily = _parquet(
        tmp_path / "daily-2020.parquet",
        """
        SELECT '000001.SZ' instrument_id, DATE '2020-01-02' trade_date,
               11.0 high, 11.0 low
        UNION ALL SELECT '000001.SZ', DATE '2020-01-03', 10.5, 9.5
        """,
    )
    limits = _parquet(
        tmp_path / "limits-2020.parquet",
        """
        SELECT '000001.SZ' instrument_id, DATE '2020-01-02' trade_date,
               11.0 upper_limit, 9.0 lower_limit, true limit_prices_usable
        UNION ALL SELECT '000001.SZ', DATE '2020-01-03', 11.0, 9.0, false
        """,
    )
    events = _parquet(
        tmp_path / "events-2020.parquet",
        """
        SELECT '000002.SZ' instrument_id, DATE '2020-01-02' trade_date,
               'S' suspension_type, NULL::VARCHAR suspension_timing
        """,
    )
    output = tmp_path / "daily-tradability-2020.parquet"
    stats = projector.project_year(
        year=2020,
        security_master=securities,
        trade_calendar=calendar,
        daily_files=(daily,),
        price_limit_files=(limits,),
        suspension_files=(events,),
        name_history=names,
        output=output,
        imported_at=datetime(2026, 7, 27, tzinfo=UTC),
    )

    with duckdb.connect(":memory:") as connection:
        rows = connection.execute(
            """
            SELECT instrument_id, trade_date, risk_status, research_eligibility,
                   suspension_state, price_limit_state, buy_state, sell_state
            FROM read_parquet(?) ORDER BY trade_date, instrument_id
            """,
            [str(output)],
        ).fetchall()
    assert rows[0][2:] == (
        "star_st",
        "excluded_special_treatment",
        "no_event",
        "usable",
        "limit_locked",
        "tradable",
    )
    assert rows[1][2:] == (
        "unknown",
        "unknown_name_status",
        "suspended",
        "missing",
        "suspended",
        "suspended",
    )
    assert rows[2][4:] == ("unknown_no_bar", "missing", "no_bar", "no_bar")
    assert rows[3][5:] == ("unusable", "unknown_limit", "unknown_limit")
    assert stats["rows"] == 6
    assert stats["unknown_name_rows"] == 4
    assert stats["confirmed_suspended_rows"] == 1
