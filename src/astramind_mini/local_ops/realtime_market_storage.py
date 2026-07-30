"""Persistence helpers for the read-only realtime service runner."""

from __future__ import annotations

import contextlib
from datetime import date, datetime
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.data.adapters import RealtimeProjectionStore
from astramind_mini.data.adapters.market_session_context import (
    SnapshotMarketSessionContext,
)
from astramind_mini.data.application.realtime_projection import RealtimeQuoteProjector
from astramind_mini.data.contracts import RealtimeMinuteBar

from .realtime_service_runtime import (
    SHANGHAI,
    RealtimeStatusStore,
    retained_open_dates,
)
from .trading_calendar import current_open_dates


def append_minute_rows(
    store: RealtimeProjectionStore,
    rows: tuple[RealtimeMinuteBar, ...],
) -> tuple[Path, ...]:
    grouped: dict[date, list[RealtimeMinuteBar]] = {}
    for row in rows:
        grouped.setdefault(row.minute.astimezone(SHANGHAI).date(), []).append(row)
    paths = []
    for market_date, dated_rows in sorted(grouped.items()):
        sealed_rows = [row.model_copy(update={"lifecycle": "sealed"}) for row in dated_rows]
        path = store.append_aggregate(
            kind="1m",
            market_date=market_date,
            rows=sealed_rows,
        )
        if path is not None:
            paths.append(path)
    return tuple(paths)


def publish_projections(
    store: RealtimeProjectionStore,
    projector: RealtimeQuoteProjector,
    now: datetime,
) -> None:
    store.publish_current(projector.project(now))
    store.publish_instruments(projector.instrument_projection(now))


def prune_retained_payloads(
    settings: Settings,
    store: RealtimeProjectionStore,
    today: date,
) -> None:
    with contextlib.suppress(FileNotFoundError, ValueError):
        retained = retained_open_dates(current_open_dates(settings.data_dir), today)
        store.prune_raw_payloads(retained_dates=retained)
        store.prune_minute_history(retained_dates=retained)


def publish_starting_status(
    settings: Settings,
    status: RealtimeStatusStore,
    today: date,
) -> None:
    context = None
    with contextlib.suppress(FileNotFoundError, ValueError, OSError):
        context = SnapshotMarketSessionContext(settings.data_dir).read_if_available(today=today)
    status.publish(
        "starting",
        market_date=today,
        completed_day_state=(
            "available"
            if context is not None and context.latest_completed_trade_date is not None
            else "unknown"
        ),
    )


__all__ = [
    "append_minute_rows",
    "prune_retained_payloads",
    "publish_projections",
    "publish_starting_status",
]
