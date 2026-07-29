"""Content-addressed, append-only filesystem adapters."""

from __future__ import annotations

import fcntl
import gzip
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from astramind_mini.contracts import DataSnapshot

from ..application.identity import bytes_hash, canonical_json, content_hash, file_hash
from ..contracts import DatasetManifest, RawRecordEnvelope
from .immutable_artifacts import (
    ImmutableConflictError,
    inspect_source_artifacts,
    publish_dataset_directory,
    verify_dataset_directory,
)


class SnapshotPointerAdvancedError(RuntimeError):
    """Raised when a publisher tries to replace a snapshot newer than its frozen base."""


def _digest(identity: str) -> str:
    value = identity.rsplit(":", 1)[-1]
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("内容身份不是合法 sha256")
    return value


def _safe_segment(value: str) -> str:
    if not value or value in {".", ".."} or any(char in value for char in "/\\:*?[]"):
        raise ValueError(f"不安全的路径片段：{value!r}")
    return value


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


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ImmutableConflictError(f"不可变身份内容冲突：{path.name}")
        return
    _atomic_write(path, payload)


class FilesystemRawRecordStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def append(self, envelope: RawRecordEnvelope, payload: object) -> Path:
        if content_hash(payload) != envelope.content_hash:
            raise ImmutableConflictError("原始响应内容哈希与信封不一致")
        provider = _safe_segment(envelope.provider)
        interface = _safe_segment(envelope.interface_name)
        day = envelope.received_at.date().isoformat()
        path = (
            self._root
            / "raw"
            / provider
            / interface
            / day
            / f"{_digest(envelope.request_identity)}.json.gz"
        )
        record = {
            "envelope": envelope.model_dump(mode="json"),
            "payload": payload,
        }
        encoded = gzip.compress(canonical_json(record), mtime=0)
        if path.exists():
            existing = gzip.decompress(path.read_bytes())
            if existing != canonical_json(record):
                raise ImmutableConflictError("同一请求身份返回了不同原始内容")
            return path
        _write_immutable(path, encoded)
        return path


class FilesystemDatasetStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, manifest: DatasetManifest, artifacts: Mapping[str, bytes]) -> Path:
        if tuple(sorted(artifacts)) != tuple(sorted(manifest.artifact_paths)):
            raise ValueError("发布文件与 DatasetManifest 不一致")
        artifact_hashes = {name: bytes_hash(payload) for name, payload in sorted(artifacts.items())}
        if content_hash(artifact_hashes) != manifest.content_hash:
            raise ImmutableConflictError("发布文件内容哈希与 DatasetManifest 不一致")
        directory = (
            self._root
            / "datasets"
            / _safe_segment(manifest.dataset_name)
            / _digest(manifest.dataset_version)
        )
        with tempfile.TemporaryDirectory(prefix="dataset-publish-") as temporary_name:
            temporary = Path(temporary_name)
            sources: dict[str, Path] = {}
            for name, payload in artifacts.items():
                safe_name = _safe_segment(name)
                source = temporary / safe_name
                source.write_bytes(payload)
                sources[safe_name] = source
            manifest_path = publish_dataset_directory(
                directory=directory,
                manifest=manifest,
                sources=sources,
            )
        self.activate(manifest, manifest_path)
        return manifest_path

    def publish_files(
        self,
        manifest: DatasetManifest,
        artifacts: Mapping[str, tuple[Path, str]],
    ) -> Path:
        if tuple(sorted(artifacts)) != tuple(sorted(manifest.artifact_paths)):
            raise ValueError("发布文件与 DatasetManifest 不一致")
        artifact_hashes = {name: expected for name, (_, expected) in sorted(artifacts.items())}
        if content_hash(artifact_hashes) != manifest.content_hash:
            raise ImmutableConflictError("发布文件内容哈希与 DatasetManifest 不一致")
        directory = (
            self._root
            / "datasets"
            / _safe_segment(manifest.dataset_name)
            / _digest(manifest.dataset_version)
        )
        sources = {_safe_segment(name): source for name, (source, _) in artifacts.items()}
        expected = {name: expected_hash for name, (_, expected_hash) in artifacts.items()}
        actual = {name: file_hash(source) for name, source in sources.items()}
        if actual != expected:
            raise ImmutableConflictError("源文件内容哈希不匹配")
        inspect_source_artifacts(manifest, sources)
        return publish_dataset_directory(
            directory=directory,
            manifest=manifest,
            sources=sources,
        )

    def activate(self, manifest: DatasetManifest, manifest_path: Path) -> None:
        directory = (
            self._root
            / "datasets"
            / _safe_segment(manifest.dataset_name)
            / _digest(manifest.dataset_version)
        )
        verified_path = verify_dataset_directory(
            directory,
            manifest,
            require_independent=True,
        )
        if manifest_path.resolve() != verified_path.resolve():
            raise ImmutableConflictError("待激活数据集清单路径不匹配")
        pointer = self._root / "current" / f"{_safe_segment(manifest.dataset_name)}.json"
        _atomic_write(
            pointer,
            canonical_json(
                {
                    "dataset_name": manifest.dataset_name,
                    "dataset_version": manifest.dataset_version,
                    "manifest_path": str(manifest_path.relative_to(self._root)),
                }
            ),
        )


class FilesystemSnapshotStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, snapshot: DataSnapshot) -> Path:
        path = self._root / "snapshots" / _digest(snapshot.snapshot_id) / "manifest.json"
        payload = canonical_json(snapshot.model_dump(mode="json"))
        if path.exists():
            existing = DataSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
            if _snapshot_identity(existing) != _snapshot_identity(snapshot):
                raise ImmutableConflictError("DataSnapshot 身份内容冲突")
            return path
        _write_immutable(path, payload)
        return path

    def get(self, snapshot_id: str) -> DataSnapshot:
        path = self._root / "snapshots" / _digest(snapshot_id) / "manifest.json"
        return DataSnapshot.model_validate_json(path.read_text(encoding="utf-8"))

    def activate(
        self,
        snapshot: DataSnapshot,
        manifest_path: Path,
        *,
        expected_snapshot_id: str | None = None,
    ) -> None:
        pointer = self._root / "current" / "data-snapshot.json"
        lock = self._root / "current" / ".data-snapshot.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("a+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            published_snapshot = self.get(snapshot.snapshot_id)
            if _snapshot_identity(published_snapshot) != _snapshot_identity(snapshot):
                raise ImmutableConflictError("待激活 DataSnapshot 身份内容冲突")
            for reference in snapshot.datasets:
                dataset_directory = (
                    self._root
                    / "datasets"
                    / _safe_segment(reference.dataset_name)
                    / _digest(reference.dataset_version)
                )
                dataset_manifest = DatasetManifest.model_validate_json(
                    (dataset_directory / "manifest.json").read_text(encoding="utf-8")
                )
                if (
                    dataset_manifest.dataset_version != reference.dataset_version
                    or dataset_manifest.content_hash != reference.content_hash
                ):
                    raise ImmutableConflictError(f"快照数据集引用冲突：{reference.dataset_name}")
                verify_dataset_directory(
                    dataset_directory,
                    dataset_manifest,
                    require_independent=True,
                )
            if expected_snapshot_id is not None and pointer.exists():
                current = json.loads(pointer.read_text(encoding="utf-8"))
                current_id = current.get("snapshot_id") if isinstance(current, dict) else None
                if current_id != expected_snapshot_id:
                    raise SnapshotPointerAdvancedError(
                        "当前 DataSnapshot 已前移，拒绝以旧基线覆盖："
                        f"expected={expected_snapshot_id},current={current_id}"
                    )
            _atomic_write(
                pointer,
                canonical_json(
                    {
                        "snapshot_id": snapshot.snapshot_id,
                        "manifest_path": str(manifest_path.relative_to(self._root)),
                    }
                ),
            )


def _snapshot_identity(snapshot: DataSnapshot) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "as_of": snapshot.as_of,
        "datasets": snapshot.datasets,
        "known_gaps": snapshot.known_gaps,
        "code_identity": snapshot.code_identity,
    }


__all__ = [
    "FilesystemDatasetStore",
    "FilesystemRawRecordStore",
    "FilesystemSnapshotStore",
    "ImmutableConflictError",
    "SnapshotPointerAdvancedError",
]
