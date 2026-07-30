from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from astramind_mini.data.application.daily_research_inputs import (
    _clip_calendar_through_target,
)


def test_daily_research_calendar_excludes_future_provider_retry_dates(
    tmp_path: Path,
) -> None:
    source = tmp_path / "calendar.parquet"
    output = tmp_path / "clipped.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            """
            COPY (
              SELECT 'SSE' exchange, calendar_date, true is_open
              FROM (VALUES
                (DATE '2026-07-29'),
                (DATE '2026-07-30'),
                (DATE '2026-08-13')
              ) dates(calendar_date)
            ) TO ? (FORMAT PARQUET)
            """,
            [str(source)],
        )

    _clip_calendar_through_target(
        source=source,
        output=output,
        target_date=date(2026, 7, 30),
    )

    with duckdb.connect(":memory:") as connection:
        assert connection.execute(
            "SELECT min(calendar_date), max(calendar_date), count(*) FROM read_parquet(?)",
            [str(output)],
        ).fetchone() == (date(2026, 7, 29), date(2026, 7, 30), 2)
