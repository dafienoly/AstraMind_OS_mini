"""Append-only gzip store for realtime raw and normalized microbatches."""

from __future__ import annotations

import gzip
from pathlib import Path

from ..application.identity import canonical_json, content_hash
from ..contracts import (
    FeedSessionReport,
    QuoteMicroBatch,
    RealtimeQuoteObservation,
)


class RealtimeMicroBatchStore:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root / "realtime" / "miniqmt"

    def append(
        self,
        report: FeedSessionReport,
        raw_messages: object,
        observations: tuple[RealtimeQuoteObservation, ...],
        *,
        sequence: int = 0,
    ) -> tuple[QuoteMicroBatch, Path]:
        raw_bytes = canonical_json(raw_messages)
        normalized_bytes = canonical_json([item.model_dump(mode="json") for item in observations])
        raw_hash = content_hash(raw_messages)
        normalized_hash = content_hash([item.model_dump(mode="json") for item in observations])
        batch_id = content_hash(
            {
                "session_id": report.session_id,
                "sequence": sequence,
                "raw_content_hash": raw_hash,
                "normalized_content_hash": normalized_hash,
            }
        )
        batch = QuoteMicroBatch(
            microbatch_id=batch_id,
            session_id=report.session_id,
            provider="miniqmt",
            sequence=sequence,
            started_at=report.subscribed_at,
            ended_at=report.ended_at,
            schema_version="miniqmt-l1-v1",
            row_count=len(observations),
            raw_content_hash=raw_hash,
            normalized_content_hash=normalized_hash,
        )
        directory = self._root / "sessions" / report.session_id.rsplit(":", 1)[-1]
        digest = batch_id.rsplit(":", 1)[-1]
        self._write_gzip(directory / f"{digest}.raw.json.gz", raw_bytes)
        self._write_gzip(directory / f"{digest}.normalized.json.gz", normalized_bytes)
        manifest_path = directory / "session.json"
        updated = report.model_copy(update={"microbatch_ids": (batch.microbatch_id,)})
        self._write_once(manifest_path, canonical_json(updated.model_dump(mode="json")))
        return batch, manifest_path

    @staticmethod
    def _write_gzip(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = gzip.compress(payload, mtime=0)
        RealtimeMicroBatchStore._write_once(path, encoded)

    @staticmethod
    def _write_once(path: Path, payload: bytes) -> None:
        try:
            with path.open("xb") as stream:
                stream.write(payload)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ValueError(f"实时制品身份冲突：{path.name}") from None


__all__ = ["RealtimeMicroBatchStore"]
