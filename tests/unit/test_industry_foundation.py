from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import duckdb
import pytest
from pydantic import ValidationError

from astramind_mini.data.adapters.event_parquet import DuckDBEventDatasetCompactor
from astramind_mini.data.application.industry_foundation_support import (
    canonicalize_l2_parents,
    five_year_windows,
    membership_overlap_stats,
)
from astramind_mini.data.application.industry_normalization import (
    normalize_index_daily,
    normalize_memberships,
    normalize_taxonomy,
)
from astramind_mini.data.ports import ProviderTable


def _table(api_name: str, rows: tuple[dict[str, object], ...]) -> ProviderTable:
    return ProviderTable(
        api_name=api_name,
        fields=tuple(rows[0]) if rows else (),
        rows=rows,
        raw_body={"code": 0},
        request_identity="sha256:" + "1" * 64,
        received_at=datetime(2026, 7, 28, tzinfo=UTC),
        source_endpoint="https://example.invalid",
    )


def test_taxonomy_is_strict_frozen_and_only_accepts_sw2021_l1() -> None:
    rows = normalize_taxonomy(
        _table(
            "index_classify",
            (
                {
                    "index_code": "801010.SI",
                    "industry_name": "农林牧渔",
                    "level": "L1",
                    "industry_code": "110000",
                    "is_pub": "1",
                    "parent_code": None,
                    "src": "SW2021",
                },
                {
                    "index_code": "801011.SI",
                    "industry_name": "种植业",
                    "level": "L2",
                    "industry_code": "110100",
                    "is_pub": "1",
                    "parent_code": "110000",
                    "src": "SW2021",
                },
            ),
        )
    )
    assert [row.industry_code for row in rows] == ["801010.SI"]
    with pytest.raises(ValidationError):
        rows[0].industry_name = "修改"


def test_l2_taxonomy_preserves_parent_and_never_enters_l1_slice() -> None:
    table = _table(
        "index_classify",
        (
            {
                "index_code": "801081.SI",
                "industry_name": "半导体",
                "level": "L2",
                "industry_code": "270100",
                "is_pub": "1",
                "parent_code": "270000",
                "src": "SW2021",
            },
        ),
    )
    row = normalize_taxonomy(table, level="L2")[0]
    assert row.level == "L2"
    assert row.parent_code == "270000"
    assert row.industry_name == "半导体"
    with pytest.raises(ValueError, match="分类为空"):
        normalize_taxonomy(table)


def test_l2_parent_is_canonical_l1_identity_and_coverage_fails_closed() -> None:
    l1 = normalize_taxonomy(
        _table(
            "index_classify",
            (
                {
                    "index_code": "801080.SI",
                    "industry_name": "电子",
                    "level": "L1",
                    "industry_code": "270000",
                    "is_pub": "1",
                    "parent_code": None,
                    "src": "SW2021",
                },
            ),
        )
    )
    l2 = normalize_taxonomy(
        _table(
            "index_classify",
            (
                {
                    "index_code": "801081.SI",
                    "industry_name": "半导体",
                    "level": "L2",
                    "industry_code": "270100",
                    "is_pub": "1",
                    "parent_code": "270000",
                    "src": "SW2021",
                },
            ),
        ),
        level="L2",
    )
    assert canonicalize_l2_parents(l1, l2)[0].parent_code == "801080.SI"
    with pytest.raises(ValueError, match="无法映射"):
        canonicalize_l2_parents(l1, (l2[0].model_copy(update={"parent_code": "999999"}),))


def test_membership_preserves_effective_interval_and_rejects_bad_interval() -> None:
    valid = _table(
        "index_member_all",
        (
            {
                "ts_code": "000001.SZ",
                "name": "合成证券",
                "in_date": "20210101",
                "out_date": "20240101",
            },
        ),
    )
    row = normalize_memberships(
        valid, industry_code="801010.SI", industry_name="农林牧渔", is_current=False
    )[0]
    assert row.effective_from.isoformat() == "2021-01-01"
    assert row.effective_to is not None and row.effective_to.isoformat() == "2024-01-01"

    invalid = _table(
        "index_member_all",
        (
            {
                "ts_code": "000001.SZ",
                "name": "合成证券",
                "in_date": "20240101",
                "out_date": "20240101",
            },
        ),
    )
    with pytest.raises(ValueError, match="区间无效"):
        normalize_memberships(
            invalid, industry_code="801010.SI", industry_name="农林牧渔", is_current=False
        )


def test_index_daily_validates_ohlc_and_does_not_invent_units() -> None:
    table = _table(
        "sw_daily",
        (
            {
                "ts_code": "801010.SI",
                "trade_date": "20250102",
                "open": 100,
                "high": 103,
                "low": 99,
                "close": 102,
                "vol": 123,
                "amount": 456,
            },
        ),
    )
    row = normalize_index_daily(table, industry_name="农林牧渔")[0]
    assert row.volume_provider_native == 123
    assert row.amount_provider_native == 456
    assert row.available_at.isoformat() == "2025-01-02T18:00:00+08:00"

    table.rows[0]["high"] = 101.995
    assert normalize_index_daily(table, industry_name="农林牧渔")

    table.rows[0]["high"] = 101
    with pytest.raises(ValueError, match="OHLC"):
        normalize_index_daily(table, industry_name="农林牧渔")


def test_five_year_windows_are_complete_and_non_overlapping() -> None:
    windows = five_year_windows(datetime(2000, 1, 1).date(), datetime(2026, 7, 24).date())
    assert windows[0][0].isoformat() == "2000-01-01"
    assert windows[-1][1].isoformat() == "2026-07-24"
    assert all(left[1].toordinal() + 1 == right[0].toordinal() for left, right in pairwise(windows))


def test_membership_overlap_allows_same_industry_but_blocks_cross_industry(
    tmp_path: Path,
) -> None:
    path = tmp_path / "members.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT * FROM VALUES
                ('L1', 'A', '000001.SZ', DATE '2020-01-01', DATE '2024-01-01'),
                ('L1', 'A', '000001.SZ', DATE '2023-01-01', NULL)
              t(level, industry_code, instrument_id, effective_from, effective_to)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(path)],
        )
    assert membership_overlap_stats(path) == {"same_industry_overlap_rows": 1}

    path.unlink()
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT * FROM VALUES
                ('L1', 'A', '000001.SZ', DATE '2020-01-01', DATE '2024-01-01'),
                ('L1', 'B', '000001.SZ', DATE '2023-01-01', NULL)
              t(level, industry_code, instrument_id, effective_from, effective_to)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(path)],
        )
    with pytest.raises(ValueError, match="跨行业重叠"):
        membership_overlap_stats(path)


def test_compactor_allows_l1_l2_projections_of_same_source_record(tmp_path: Path) -> None:
    source = tmp_path / "source.parquet"
    output = tmp_path / "output.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT * FROM VALUES
                ('L1', '801080.SI', '000001.SZ', DATE '2021-01-01', NULL, 'sha256:same'),
                ('L2', '801081.SI', '000001.SZ', DATE '2021-01-01', NULL, 'sha256:same')
              t(level, industry_code, instrument_id, effective_from, effective_to,
                source_record_hash)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(source)],
        )
    stats = DuckDBEventDatasetCompactor().compact(
        source_files=(source,),
        output=output,
        order_by=("level", "industry_code"),
        date_column="effective_from",
        identity_columns=(
            "level",
            "industry_code",
            "instrument_id",
            "effective_from",
            "effective_to",
        ),
    )
    assert stats["rows"] == 2


def test_compactor_blocks_conflicting_rows_for_same_observation_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT * FROM VALUES
                ('L2', '801081.SI', '000001.SZ', DATE '2021-01-01', NULL,
                 'sha256:first'),
                ('L2', '801081.SI', '000001.SZ', DATE '2021-01-01', NULL,
                 'sha256:second')
              t(level, industry_code, instrument_id, effective_from, effective_to,
                source_record_hash)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(source)],
        )
    with pytest.raises(ValueError, match="内容身份重复"):
        DuckDBEventDatasetCompactor().compact(
            source_files=(source,),
            output=tmp_path / "output.parquet",
            order_by=("level", "industry_code"),
            date_column="effective_from",
            identity_columns=(
                "level",
                "industry_code",
                "instrument_id",
                "effective_from",
                "effective_to",
            ),
        )
