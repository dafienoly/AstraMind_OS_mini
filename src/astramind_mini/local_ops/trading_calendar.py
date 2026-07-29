"""Read the current versioned SSE trading calendar without provider access."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb


def current_open_dates(data_root: Path) -> tuple[date, ...]:
    pointer = _read_object(data_root / "current" / "trade_calendar.json")
    relative = Path(str(pointer.get("manifest_path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("交易日历指针路径无效")
    manifest = _read_object(data_root / relative)
    artifacts = manifest.get("artifact_paths")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise ValueError("交易日历制品清单无效")
    artifact = Path(str(artifacts[0]))
    if artifact.is_absolute() or ".." in artifact.parts:
        raise ValueError("交易日历制品路径无效")
    calendar_path = data_root / relative.parent / artifact
    with duckdb.connect() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT calendar_date
            FROM read_parquet(?)
            WHERE exchange = 'SSE' AND is_open
            ORDER BY calendar_date
            """,
            [str(calendar_path)],
        ).fetchall()
    return tuple(row[0] for row in rows if isinstance(row[0], date))


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 对象无效：{path.name}")
    return value


__all__ = ["current_open_dates"]
