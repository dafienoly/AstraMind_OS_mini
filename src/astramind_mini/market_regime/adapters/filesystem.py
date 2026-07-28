"""Content-addressed local rotation evidence store."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..contracts import MarketRotationSnapshot
from ..domain.identity import content_hash


class FilesystemRotationStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, snapshot: MarketRotationSnapshot) -> Path:
        self._verify(snapshot)
        digest = snapshot.content_hash.removeprefix("sha256:")
        path = self._root / "snapshots" / digest / "snapshot.json"
        payload = _json_bytes(snapshot.model_dump(mode="json"))
        if path.exists() and path.read_bytes() != payload:
            raise ValueError("同一轮动身份内容冲突")
        if not path.exists():
            _atomic_write(path, payload)
        _atomic_write(
            self._root / "current.json",
            _json_bytes(
                {
                    "rotation_snapshot_id": snapshot.rotation_snapshot_id,
                    "content_hash": snapshot.content_hash,
                    "artifact_path": str(path.relative_to(self._root)),
                }
            ),
        )
        return path

    def get_current(self) -> MarketRotationSnapshot:
        pointer = json.loads((self._root / "current.json").read_text(encoding="utf-8"))
        if not isinstance(pointer, dict):
            raise ValueError("轮动当前指针无效")
        relative = Path(str(pointer.get("artifact_path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("轮动当前指针路径无效")
        snapshot = MarketRotationSnapshot.model_validate_json(
            (self._root / relative).read_text(encoding="utf-8")
        )
        self._verify(snapshot)
        if pointer.get("content_hash") != snapshot.content_hash:
            raise ValueError("轮动当前指针身份冲突")
        return snapshot

    def _verify(self, snapshot: MarketRotationSnapshot) -> None:
        identity = {
            "data_snapshot_id": snapshot.data_snapshot_id,
            "as_of": snapshot.as_of,
            "formula": snapshot.formula.model_dump(mode="json"),
            "dates": snapshot.dates,
            "points": [point.model_dump(mode="json") for point in snapshot.points],
            "events": [event.model_dump(mode="json") for event in snapshot.events],
            "known_gaps": sorted(snapshot.known_gaps),
        }
        digest = content_hash(identity)
        if snapshot.content_hash != digest or snapshot.rotation_snapshot_id != "rotation:" + digest:
            raise ValueError("轮动快照内容身份校验失败")


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["FilesystemRotationStore"]
