"""Deterministic skops serialization for reproducible production model identities."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

import skops.io  # type: ignore[import-untyped]

from ..artifacts import SerializedModel

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def serialize_deterministically(model: object) -> SerializedModel:
    """Remove process identities and ZIP metadata while preserving the skops graph."""

    source = skops.io.dumps(model)
    payload = _canonicalize_skops_archive(source)
    untrusted = skops.io.get_untrusted_types(data=payload)
    if untrusted:
        raise ValueError(f"模型产物包含未受信类型：{','.join(sorted(untrusted))}")
    return SerializedModel(payload=payload, content_hash=_bytes_hash(payload))


def _canonicalize_skops_archive(payload: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        names = frozenset(source.namelist())
        schema = json.loads(source.read("schema.json"))
        normalizer = _SkopsGraphNormalizer(names)
        normalized = normalizer.normalize(schema)
        arrays = {
            normalized_name: source.read(source_name)
            for source_name, normalized_name in normalizer.array_names.items()
        }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, array in sorted(arrays.items()):
            _write_member(archive, name, array)
        encoded_schema = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        _write_member(archive, "schema.json", encoded_schema)
    return output.getvalue()


class _SkopsGraphNormalizer:
    def __init__(self, archive_names: frozenset[str]) -> None:
        self._archive_names = archive_names
        self._object_ids: dict[int, int] = {}
        self.array_names: dict[str, str] = {}

    def normalize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._normalize_item(key, item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.normalize(item) for item in value]
        if isinstance(value, str) and value != "schema.json" and value in self._archive_names:
            return self.array_names.setdefault(
                value,
                f"array-{len(self.array_names):06d}.npy",
            )
        return value

    def _normalize_item(self, key: str, value: Any) -> Any:
        if key == "__id__" and isinstance(value, int):
            return self._object_ids.setdefault(value, len(self._object_ids) + 1)
        return self.normalize(value)


def _write_member(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    information = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
    information.compress_type = zipfile.ZIP_STORED
    information.external_attr = 0o600 << 16
    archive.writestr(information, payload)


def _bytes_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


__all__ = ["serialize_deterministically"]
