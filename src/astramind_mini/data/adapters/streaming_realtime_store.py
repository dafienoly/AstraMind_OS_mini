"""Append immutable microbatches and finalize one long-lived feed session."""

from __future__ import annotations

import gzip
from datetime import datetime
from pathlib import Path

from ..application.identity import canonical_json, content_hash
from ..contracts import FeedSessionReport, QuoteMicroBatch, RealtimeQuoteObservation


class StreamingRealtimeStore:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root / "realtime" / "miniqmt"

    def append(
        self,
        *,
        session_id: str,
        sequence: int,
        started_at: datetime,
        ended_at: datetime,
        raw_messages: object,
        observations: tuple[RealtimeQuoteObservation, ...],
    ) -> tuple[QuoteMicroBatch, Path]:
        normalized = [item.model_dump(mode="json") for item in observations]
        raw_hash = content_hash(raw_messages)
        normalized_hash = content_hash(normalized)
        batch_id = content_hash(
            {
                "session_id": session_id,
                "sequence": sequence,
                "raw_content_hash": raw_hash,
                "normalized_content_hash": normalized_hash,
            }
        )
        batch = QuoteMicroBatch(
            microbatch_id=batch_id,
            session_id=session_id,
            provider="miniqmt",
            sequence=sequence,
            started_at=started_at,
            ended_at=ended_at,
            schema_version="miniqmt-l1-v2",
            row_count=len(observations),
            raw_content_hash=raw_hash,
            normalized_content_hash=normalized_hash,
        )
        directory = self._directory(session_id)
        digest = batch_id.rsplit(":", 1)[-1]
        _write_once(
            directory / f"{digest}.raw.json.gz",
            gzip.compress(canonical_json(raw_messages), mtime=0),
        )
        _write_once(
            directory / f"{digest}.normalized.json.gz",
            gzip.compress(canonical_json(normalized), mtime=0),
        )
        manifest = directory / "microbatches" / f"{sequence:08d}-{digest}.json"
        _write_once(manifest, canonical_json(batch.model_dump(mode="json")))
        return batch, manifest

    def finalize(self, report: FeedSessionReport) -> Path:
        directory = self._directory(report.session_id)
        batches = sorted((directory / "microbatches").glob("*.json"))
        ids = tuple(
            QuoteMicroBatch.model_validate_json(path.read_text(encoding="utf-8")).microbatch_id
            for path in batches
        )
        completed = report.model_copy(update={"microbatch_ids": ids})
        path = directory / "session.json"
        _write_once(path, canonical_json(completed.model_dump(mode="json")))
        return path

    def _directory(self, session_id: str) -> Path:
        return self._root / "sessions" / session_id.rsplit(":", 1)[-1]


def _write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f"实时微批不可变身份冲突：{path.name}") from None


__all__ = ["StreamingRealtimeStore"]
