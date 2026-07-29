"""Redacted, append-only diagnostics for Paper Windows runners."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MAX_STREAM_CHARS = 32_000
_INTEROP_MARKERS = (
    "utilacceptvsock",
    "createprocessentrycommon",
    "wsl_e_",
    "wsl error",
    "failed to translate",
)
_QMT_DISCONNECTED_MARKERS = (
    "qmt_not_connected",
    "not connected",
    "connection refused",
    "connect failed",
    "连接失败",
    "未连接",
)


def classify_runner_failure(
    *,
    stdout: bytes,
    stderr: bytes,
    body: dict[str, Any] | None,
    default: str,
) -> str:
    """Return a stable operator-facing failure code without exposing provider text."""

    combined = (stdout + b"\n" + stderr).decode("utf-8-sig", errors="replace").lower()
    if any(marker in combined for marker in _INTEROP_MARKERS):
        return "windows_interop_unavailable"
    runner_code = str((body or {}).get("runner_error_code", "")).lower()
    if runner_code == "quote_stale":
        return "canary_quote_stale"
    if runner_code == "qmt_not_connected" or any(
        marker in combined for marker in _QMT_DISCONNECTED_MARKERS
    ):
        return "qmt_not_connected"
    return default


def record_runner_diagnostic(
    *,
    root: Path | None,
    runner: str,
    stdout: bytes,
    stderr: bytes,
    returncode: int | None,
    outcome: str,
    secrets: tuple[str, ...] = (),
) -> Path | None:
    """Persist bounded stdout/stderr after removing local paths and supplied secrets."""

    if root is None:
        return None
    observed_at = datetime.now(UTC)
    payload = {
        "schema_version": 1,
        "runner": runner,
        "observed_at": observed_at.isoformat(),
        "returncode": returncode,
        "outcome": outcome,
        "stdout": _redact(stdout, secrets),
        "stderr": _redact(stderr, secrets),
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{observed_at:%Y%m%dT%H%M%S%fZ}-{runner}-{digest[:12]}.json"
    target.write_text(canonical + "\n", encoding="utf-8")
    return target


def _redact(payload: bytes, secrets: tuple[str, ...]) -> dict[str, object]:
    text = payload.decode("utf-8-sig", errors="replace")
    original_length = len(text)
    for sensitive_value in secrets:
        if sensitive_value:
            text = text.replace(sensitive_value, "<redacted>")
    text = re.sub(r"(?i)[a-z]:\\users\\[^\\\s\"']+", r"C:\\Users\\<redacted>", text)
    text = re.sub(r"(?i)/mnt/[a-z]/users/[^/\s\"']+", "/mnt/c/Users/<redacted>", text)
    text = re.sub(r"/home/[^/\s\"']+", "/home/<redacted>", text)
    text = re.sub(
        r'(?i)(account(?:_id|selector)?|token|secret|password)(["\s:=]+)[^,\s"}]+',
        r"\1\2<redacted>",
        text,
    )
    truncated = len(text) > _MAX_STREAM_CHARS
    return {
        "text": text[:_MAX_STREAM_CHARS],
        "original_chars": original_length,
        "truncated": truncated,
    }


__all__ = ["classify_runner_failure", "record_runner_diagnostic"]
