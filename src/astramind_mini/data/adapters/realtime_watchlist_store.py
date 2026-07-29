"""Local, read-only-market watchlist persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class RealtimeWatchlistStore:
    def __init__(self, control_root: Path) -> None:
        self._path = control_root / "market-watchlist" / "watchlist.json"

    def read(self) -> tuple[str, ...]:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ()
        codes = value.get("instrument_ids", [])
        if not isinstance(codes, list):
            raise ValueError("自选清单格式无效")
        return tuple(str(code) for code in codes)

    def write(self, codes: tuple[str, ...]) -> tuple[str, ...]:
        unique = tuple(dict.fromkeys(codes))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".watchlist.", dir=self._path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    {"schema_version": "1.0.0", "instrument_ids": unique},
                    stream,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        finally:
            temporary.unlink(missing_ok=True)
        return unique


__all__ = ["RealtimeWatchlistStore"]
