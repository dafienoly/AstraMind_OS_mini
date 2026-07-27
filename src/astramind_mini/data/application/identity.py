"""Canonical identities used by immutable Data-context artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")


def content_hash(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def schema_fingerprint(rows: object) -> str:
    fields: set[str] = set()
    if isinstance(rows, Mapping):
        fields.update(str(key) for key in rows)
    elif isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                fields.update(str(key) for key in row)
    return content_hash(sorted(fields))


def _json_default(value: Any) -> str:
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    raise TypeError(f"不支持规范 JSON 类型：{type(value).__name__}")


__all__ = [
    "bytes_hash",
    "canonical_json",
    "content_hash",
    "file_hash",
    "schema_fingerprint",
]
