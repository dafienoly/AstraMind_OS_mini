"""Append-only filesystem store for read-only model activations."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .contracts import MarketModelFamily, ModelActivation
from .identity import activation_content_hash


class ModelActivationStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, activation: ModelActivation) -> Path:
        payload = _json_bytes(activation.model_dump(mode="json"))
        digest = activation_content_hash(activation).removeprefix("sha256:")
        expected_id = f"model-activation:{digest}"
        if activation.activation_id != expected_id:
            raise ValueError("模型激活身份与内容不一致")
        history = self._root / "history" / activation.model_family / f"{digest}.json"
        if history.exists() and history.read_bytes() != payload:
            raise ValueError("同一模型激活身份内容冲突")
        if not history.exists():
            _atomic_write(history, payload)
        pointer = {
            "activation_id": activation.activation_id,
            "content_hash": "sha256:" + digest,
            "artifact_path": str(history.relative_to(self._root)),
        }
        _atomic_write(
            self._root / "current" / f"{activation.model_family}.json",
            _json_bytes(pointer),
        )
        return history

    def current(self, family: MarketModelFamily) -> ModelActivation:
        pointer_path = self._root / "current" / f"{family}.json"
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if not isinstance(pointer, dict):
            raise ValueError("模型激活当前指针无效")
        relative = Path(str(pointer.get("artifact_path", "")))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("模型激活当前指针路径无效")
        activation = ModelActivation.model_validate_json(
            (self._root / relative).read_text(encoding="utf-8")
        )
        digest = activation_content_hash(activation)
        if pointer.get("content_hash") != digest:
            raise ValueError("模型激活当前指针内容哈希不一致")
        if activation.model_family != family:
            raise ValueError("模型激活当前指针家族不一致")
        return activation


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


__all__ = ["ModelActivationStore"]
