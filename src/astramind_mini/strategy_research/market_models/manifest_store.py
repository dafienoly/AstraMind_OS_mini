"""Append-only store for exact market-model manifests."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .contracts import MarketModelManifest
from .identity import manifest_content_hash


class MarketModelManifestStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, manifest: MarketModelManifest) -> Path:
        digest = manifest_content_hash(manifest).removeprefix("sha256:")
        if manifest.manifest_id != f"market-model-manifest:{digest}":
            raise ValueError("市场模型清单身份与内容不一致")
        path = self._root / "manifests" / manifest.model_family / f"{digest}.json"
        payload = _json_bytes(manifest.model_dump(mode="json"))
        if path.exists() and path.read_bytes() != payload:
            raise ValueError("同一市场模型清单身份内容冲突")
        if not path.exists():
            _atomic_write(path, payload)
        return path

    def load(self, manifest_id: str) -> MarketModelManifest:
        digest = _digest(manifest_id)
        matches = tuple((self._root / "manifests").glob(f"*/*{digest}.json"))
        if len(matches) != 1:
            raise FileNotFoundError(f"市场模型清单不存在或不唯一：{manifest_id}")
        manifest = MarketModelManifest.model_validate_json(matches[0].read_text(encoding="utf-8"))
        if manifest.manifest_id != manifest_id:
            raise ValueError("市场模型清单路径与身份不一致")
        if manifest_content_hash(manifest) != f"sha256:{digest}":
            raise ValueError("市场模型清单内容哈希不一致")
        return manifest


def _digest(value: str) -> str:
    prefix = "market-model-manifest:"
    digest = value.removeprefix(prefix)
    if not value.startswith(prefix) or len(digest) != 64:
        raise ValueError("市场模型清单身份格式无效")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("市场模型清单身份格式无效")
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


__all__ = ["MarketModelManifestStore"]
