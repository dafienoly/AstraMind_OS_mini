"""Canonical content identity for Market Regime evidence."""

import hashlib
import json
from typing import Any


def content_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_default(value: Any) -> str:
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    raise TypeError(f"不支持规范 JSON 类型：{type(value).__name__}")


__all__ = ["content_hash"]
