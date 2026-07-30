"""Recompute which normalized realtime observations require minute output."""

from __future__ import annotations

import gzip
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from ..application.identity import content_hash
from ..application.realtime_minute_replay import RealtimeMinuteReplay
from ..contracts.realtime import QuoteMicroBatch, RealtimeQuoteObservation
from ..contracts.realtime_projection import RealtimeMinuteBar


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


def replay_closed_minutes(
    rows: tuple[RealtimeQuoteObservation, ...],
    *,
    session_id: str,
    ended_at: datetime,
) -> tuple[RealtimeMinuteBar, ...]:
    replay = RealtimeMinuteReplay(session_id)
    replay.ingest(rows)
    closed = (*replay.drain_closed(), *replay.close_completed(ended_at))
    return tuple(row.rebuild(lifecycle="sealed") for row in closed)


__all__ = ["replay_closed_minutes", "verified_observations"]
