"""Recompute which normalized realtime observations require minute output."""

from __future__ import annotations

import gzip
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter

from ..application.identity import content_hash
from ..contracts.realtime import QuoteMicroBatch, RealtimeQuoteObservation

SHANGHAI = ZoneInfo("Asia/Shanghai")


def verified_observations(
    directory: Path,
    manifests: Sequence[Path],
) -> tuple[RealtimeQuoteObservation, ...]:
    rows: list[RealtimeQuoteObservation] = []
    for manifest_path in manifests:
        batch = QuoteMicroBatch.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        digest = batch.microbatch_id.rsplit(":", 1)[-1]
        normalized_path = directory / f"{digest}.normalized.json.gz"
        payload = TypeAdapter(tuple[RealtimeQuoteObservation, ...]).validate_json(
            gzip.decompress(normalized_path.read_bytes())
        )
        if (
            len(payload) != batch.row_count
            or content_hash([row.model_dump(mode="json") for row in payload])
            != batch.normalized_content_hash
        ):
            raise ValueError("实时会话规范微批内容身份不一致")
        rows.extend(payload)
    return tuple(rows)


def expected_minute_keys(
    rows: tuple[RealtimeQuoteObservation, ...],
    *,
    ended_at: datetime,
) -> set[tuple[str, datetime]]:
    prior: dict[str, tuple[float, float]] = {}
    expected: set[tuple[str, datetime]] = set()
    completed_before = ended_at.astimezone(SHANGHAI).replace(second=0, microsecond=0)
    for row in rows:
        if row.last_price is None:
            continue
        previous = prior.get(row.instrument_id)
        volume = row.volume if row.volume is not None else (previous[0] if previous else 0)
        amount = row.amount if row.amount is not None else (previous[1] if previous else 0)
        prior[row.instrument_id] = (volume, amount)
        if previous is None or (volume == previous[0] and amount == previous[1]):
            continue
        minute = _market_minute(row)
        if minute < completed_before:
            expected.add((row.instrument_id, minute))
    return expected


def _market_minute(row: RealtimeQuoteObservation) -> datetime:
    value = (
        datetime.fromtimestamp(row.market_time_ms / 1000, tz=SHANGHAI)
        if row.market_time_ms is not None and row.market_time_ms > 1_000_000_000_000
        else row.received_at.astimezone(SHANGHAI)
    )
    return value.replace(second=0, microsecond=0)


__all__ = ["expected_minute_keys", "verified_observations"]
