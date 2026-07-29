"""Content-addressed skops artifact store with fail-closed reads."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import skops.io  # type: ignore[import-untyped]


@dataclass(frozen=True)
class SerializedModel:
    payload: bytes
    content_hash: str


class SkopsArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def serialize(self, model: object) -> SerializedModel:
        payload = skops.io.dumps(model)
        untrusted = skops.io.get_untrusted_types(data=payload)
        if untrusted:
            raise ValueError(f"模型产物包含未受信类型：{','.join(sorted(untrusted))}")
        return SerializedModel(payload=payload, content_hash=_bytes_hash(payload))

    def publish(self, serialized: SerializedModel) -> Path:
        _verify_payload(serialized)
        digest = serialized.content_hash.removeprefix("sha256:")
        path = self._root / "artifacts" / digest / "model.skops"
        if path.exists() and path.read_bytes() != serialized.payload:
            raise ValueError("同一模型产物身份内容冲突")
        if not path.exists():
            _atomic_write(path, serialized.payload)
        return path

    def load(self, content_hash: str) -> Any:
        digest = _validated_digest(content_hash)
        payload = (self._root / "artifacts" / digest / "model.skops").read_bytes()
        if _bytes_hash(payload) != content_hash:
            raise ValueError("模型产物内容哈希不一致")
        untrusted = skops.io.get_untrusted_types(data=payload)
        if untrusted:
            raise ValueError(f"模型产物包含未受信类型：{','.join(sorted(untrusted))}")
        return skops.io.loads(payload, trusted=[])


def _verify_payload(serialized: SerializedModel) -> None:
    if _bytes_hash(serialized.payload) != serialized.content_hash:
        raise ValueError("序列化模型身份与内容不一致")


def _validated_digest(content_hash: str) -> str:
    prefix = "sha256:"
    digest = content_hash.removeprefix(prefix)
    if not content_hash.startswith(prefix) or len(digest) != 64:
        raise ValueError("模型产物哈希格式无效")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("模型产物哈希格式无效")
    return digest


def _bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


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


__all__ = ["SerializedModel", "SkopsArtifactStore"]
