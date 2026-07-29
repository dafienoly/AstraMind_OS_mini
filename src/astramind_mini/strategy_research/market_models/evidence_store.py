"""Append-only evidence store with content and manifest verification."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .contracts import MarketModelEvidenceBundle
from .evidence import evidence_content_hash


class MarketModelEvidenceStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, bundle: MarketModelEvidenceBundle) -> Path:
        expected_hash = evidence_content_hash(bundle)
        expected_id = "market-model-evidence:" + expected_hash.removeprefix("sha256:")
        if bundle.content_hash != expected_hash or bundle.evidence_bundle_id != expected_id:
            raise ValueError("市场模型证据身份与内容不一致")
        digest = expected_hash.removeprefix("sha256:")
        path = self._root / "evidence" / digest / "bundle.json"
        payload = _json_bytes(bundle.model_dump(mode="json"))
        if path.exists() and path.read_bytes() != payload:
            raise ValueError("同一市场模型证据身份内容冲突")
        if not path.exists():
            _atomic_write(path, payload)
        return path

    def load(self, evidence_bundle_id: str) -> MarketModelEvidenceBundle:
        digest = _digest(evidence_bundle_id, "market-model-evidence:")
        path = self._root / "evidence" / digest / "bundle.json"
        bundle = MarketModelEvidenceBundle.model_validate_json(path.read_text(encoding="utf-8"))
        if bundle.evidence_bundle_id != evidence_bundle_id:
            raise ValueError("市场模型证据路径与身份不一致")
        if bundle.content_hash != evidence_content_hash(bundle):
            raise ValueError("市场模型证据内容哈希不一致")
        return bundle


def _digest(value: str, prefix: str) -> str:
    digest = value.removeprefix(prefix)
    if not value.startswith(prefix) or len(digest) != 64:
        raise ValueError("市场模型证据身份格式无效")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("市场模型证据身份格式无效")
    return digest


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


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


__all__ = ["MarketModelEvidenceStore"]
