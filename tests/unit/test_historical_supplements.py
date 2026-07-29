from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from astramind_mini.data.application.daily_research_inputs import (
    _invalidate_incomplete_market_cache,
)
from astramind_mini.data.application.historical_supplements import (
    validate_daily_market_coverage,
)

TARGET = date(2026, 7, 29)


def test_daily_market_coverage_matches_daily_basic(tmp_path: Path) -> None:
    daily = _parquet(tmp_path / "daily.parquet", ("000001.SZ", "000002.SZ"))
    basic = _parquet(tmp_path / "basic.parquet", ("000001.SZ", "000002.SZ"))

    assert validate_daily_market_coverage(daily, basic, TARGET) == (2, 2)


def test_daily_market_coverage_rejects_missing_security(tmp_path: Path) -> None:
    daily = _parquet(tmp_path / "daily.parquet", ("000001.SZ",))
    basic = _parquet(tmp_path / "basic.parquet", ("000001.SZ", "000002.SZ"))

    with pytest.raises(ValueError, match="missing=1"):
        validate_daily_market_coverage(daily, basic, TARGET)


def test_incomplete_cached_market_day_is_invalidated(tmp_path: Path) -> None:
    daily = _parquet(tmp_path / "daily.parquet", ("000001.SZ",))
    basic = _parquet(tmp_path / "basic.parquet", ("000001.SZ", "000002.SZ"))
    entry = {
        "daily": str(daily),
        "daily_request_identity": "sha256:old",
        "daily_received_at": "2026-07-29T18:00:00+08:00",
        "adj_factor": "kept",
    }
    state: dict[str, object] = {"supplements": {TARGET.isoformat(): entry}}

    _invalidate_incomplete_market_cache(
        market_state=state,
        market_state_path=tmp_path / "market-state.json",
        daily_basic_path=basic,
        target_date=TARGET,
    )

    assert entry == {"adj_factor": "kept"}


def _parquet(path: Path, instruments: tuple[str, ...]) -> Path:
    rows = [(instrument, TARGET) for instrument in instruments]
    with duckdb.connect(":memory:") as connection:
        connection.execute("CREATE TABLE observations(instrument_id VARCHAR, trade_date DATE)")
        connection.executemany("INSERT INTO observations VALUES (?, ?)", rows)
        connection.execute(f"COPY observations TO '{path.as_posix()}' (FORMAT PARQUET)")
    return path
