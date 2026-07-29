from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from astramind_mini.data.application.provider_lineage import (
    market_artifact_matches_epoch,
    market_source_attribution,
)


def _write_rows(path: Path, rows: tuple[tuple[str, str, str, str], ...]) -> None:
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            CREATE TABLE rows (
                provider VARCHAR,
                source_endpoint VARCHAR,
                instrument_id VARCHAR,
                trade_date DATE
            )
            """
        )
        connection.executemany("INSERT INTO rows VALUES (?, ?, ?, ?)", rows)
        connection.execute(
            "COPY rows TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(path)],
        )


def test_approved_date_cutover_is_published_as_provider_lineage(tmp_path: Path) -> None:
    path = tmp_path / "market.parquet"
    _write_rows(
        path,
        (
            ("tushare", "legacy", "600519.SH", "2026-07-28"),
            ("miniqmt", "xtdata", "600519.SH", "2026-07-29"),
        ),
    )

    attribution = market_source_attribution((path,))

    assert attribution.provider == "date-bound-cutover"
    assert attribution.source_endpoint == "multiple-provider-endpoints"
    assert [item.provider for item in attribution.provider_lineage] == [
        "tushare",
        "miniqmt",
    ]
    legacy_end = attribution.provider_lineage[0].effective_to
    assert legacy_end is not None
    assert legacy_end.isoformat() == "2026-07-28"
    assert attribution.provider_lineage[1].effective_from.isoformat() == "2026-07-29"
    assert attribution.provider_lineage[1].effective_to is None


@pytest.mark.parametrize(
    "rows",
    (
        (
            ("miniqmt", "xtdata", "600519.SH", "2026-07-28"),
            ("tushare", "legacy", "600519.SH", "2026-07-29"),
        ),
        (
            ("tushare", "legacy", "600519.SH", "2026-07-29"),
            ("miniqmt", "xtdata", "000001.SZ", "2026-07-29"),
        ),
    ),
)
def test_wrong_side_or_same_day_provider_mix_is_blocked(
    tmp_path: Path,
    rows: tuple[tuple[str, str, str, str], ...],
) -> None:
    path = tmp_path / "market.parquet"
    _write_rows(path, rows)

    with pytest.raises(ValueError, match="日期切换边界无效"):
        market_source_attribution((path,))


def test_cached_market_artifact_must_match_its_provider_epoch(tmp_path: Path) -> None:
    path = tmp_path / "market.parquet"
    _write_rows(
        path,
        (("tushare", "legacy", "600519.SH", "2026-07-29"),),
    )

    assert not market_artifact_matches_epoch(path, date(2026, 7, 29))
    assert market_artifact_matches_epoch(path, date(2026, 7, 28)) is False
