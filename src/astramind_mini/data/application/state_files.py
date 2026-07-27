"""Small atomic state files for resumable local imports."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .identity import canonical_json, file_hash


def load_state(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("导入状态格式无效")
    return value


def save_state(path: Path, value: dict[str, object]) -> None:
    write_bytes_atomic(path, canonical_json(value))


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def year_is_intact(value: dict[str, object]) -> bool:
    pairs = (
        ("daily_path", "daily_hash"),
        ("factor_path", "factor_hash"),
    )
    return all(
        Path(str(value[path_key])).is_file()
        and file_hash(Path(str(value[path_key]))) == value[hash_key]
        for path_key, hash_key in pairs
    )


def constraint_year_is_intact(
    value: dict[str, object],
    *,
    require_price_limit: bool,
) -> bool:
    pairs = [
        ("daily_basic_path", "daily_basic_hash"),
        ("suspension_event_path", "suspension_event_hash"),
    ]
    if require_price_limit:
        pairs.append(("price_limit_path", "price_limit_hash"))
    return all(
        Path(str(value[path_key])).is_file()
        and file_hash(Path(str(value[path_key]))) == value[hash_key]
        for path_key, hash_key in pairs
    )


def status_year_is_intact(value: dict[str, object]) -> bool:
    path = Path(str(value.get("path", "")))
    return path.is_file() and file_hash(path) == value.get("hash")


def corporate_year_is_intact(value: dict[str, object]) -> bool:
    pairs = (("path", "hash"), ("anchor_path", "anchor_hash"))
    return all(
        Path(str(value.get(path_key, ""))).is_file()
        and file_hash(Path(str(value[path_key]))) == value.get(hash_key)
        for path_key, hash_key in pairs
    )


__all__ = [
    "constraint_year_is_intact",
    "corporate_year_is_intact",
    "load_state",
    "save_state",
    "status_year_is_intact",
    "write_bytes_atomic",
    "year_is_intact",
]
