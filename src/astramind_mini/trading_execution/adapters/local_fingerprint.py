"""Private local key used only to create stable redacted broker fingerprints."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def local_fingerprint_key(root: Path) -> str:
    path = root / "fingerprint.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(secrets.token_hex(32))
    return path.read_text(encoding="utf-8").strip()


__all__ = ["local_fingerprint_key"]
