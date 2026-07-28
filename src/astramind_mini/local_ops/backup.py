"""Consistent external control-plane backups with bounded retention."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import uuid
from collections.abc import Mapping
from contextlib import suppress
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from .contracts import BackupFile, BackupManifest
from .identity import operations_hash

BackupReason = Literal["daily_close", "pre_migration", "pre_first_broker_write", "manual"]


class LocalBackupService:
    def __init__(self, *, repository_root: Path, backup_root: Path) -> None:
        self._repository_root = repository_root.resolve()
        self._backup_root = backup_root.expanduser().resolve()
        _validate_external_root(self._repository_root, self._backup_root)
        self._namespace = self._backup_root / "astramind-mini"

    def create(
        self,
        *,
        reason: BackupReason,
        logical_date: date,
        created_at: datetime,
        sqlite_sources: Mapping[str, Path],
        required_sqlite: frozenset[str],
        pointer_directory: Path,
        configuration_fingerprint: str,
    ) -> BackupManifest:
        if created_at.tzinfo is None:
            raise ValueError("备份时间必须带时区")
        staging = self._namespace / ".staging" / uuid.uuid4().hex
        staging.mkdir(parents=True, exist_ok=False)
        files: list[BackupFile] = []
        missing: list[str] = []
        try:
            for logical_name, source in sorted(sqlite_sources.items()):
                if not source.is_file():
                    if logical_name in required_sqlite:
                        missing.append(logical_name)
                    continue
                relative = Path("sqlite") / f"{logical_name}.sqlite3"
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                _backup_sqlite(source, target)
                files.append(_backup_file(logical_name, "sqlite", relative, target))
            pointers = sorted(pointer_directory.glob("*.json"))
            if not pointers:
                missing.append("data_current_pointers")
            for source in pointers:
                relative = Path("pointers") / source.name
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                files.append(_backup_file(f"pointer:{source.stem}", "pointer", relative, target))

            manifest = _manifest(
                reason=reason,
                logical_date=logical_date,
                created_at=created_at,
                files=tuple(files),
                missing_sources=tuple(sorted(missing)),
                configuration_fingerprint=configuration_fingerprint,
            )
            manifest_path = staging / "manifest.json"
            manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            final = (
                self._namespace
                / "daily"
                / logical_date.isoformat()
                / manifest.backup_id.rsplit(":", 1)[-1]
            )
            final.parent.mkdir(parents=True, exist_ok=True)
            if final.exists():
                existing = BackupManifest.model_validate_json(
                    (final / "manifest.json").read_text(encoding="utf-8")
                )
                if existing != manifest:
                    raise ValueError("备份身份发生内容冲突")
                shutil.rmtree(staging)
            else:
                os.replace(staging, final)
            return manifest
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def prune(self) -> tuple[str, ...]:
        records = _backup_records(self._namespace)
        retained = retained_backup_ids(tuple(item[1] for item in records))
        removed = []
        for path, manifest in records:
            if manifest.backup_id in retained:
                continue
            _safe_remove_backup(path, self._namespace)
            removed.append(manifest.backup_id)
        return tuple(sorted(removed))

    @property
    def namespace(self) -> Path:
        return self._namespace


def retained_backup_ids(manifests: tuple[BackupManifest, ...]) -> frozenset[str]:
    ordered = sorted(
        manifests,
        key=lambda item: (item.logical_date, item.created_at, item.backup_id),
        reverse=True,
    )
    retained = {item.backup_id for item in ordered[:30]}
    month_end: dict[str, BackupManifest] = {}
    for item in ordered:
        month_end.setdefault(item.logical_date.strftime("%Y-%m"), item)
    for month in sorted(month_end, reverse=True)[:12]:
        retained.add(month_end[month].backup_id)
    return frozenset(retained)


def configuration_fingerprint(values: Mapping[str, object]) -> str:
    return operations_hash(dict(sorted(values.items())))


def _manifest(
    *,
    reason: BackupReason,
    logical_date: date,
    created_at: datetime,
    files: tuple[BackupFile, ...],
    missing_sources: tuple[str, ...],
    configuration_fingerprint: str,
) -> BackupManifest:
    status: Literal["complete", "partial"] = "complete" if not missing_sources else "partial"
    identity = {
        "reason": reason,
        "logical_date": logical_date,
        "created_at": created_at,
        "status": status,
        "files": [item.model_dump(mode="json") for item in files],
        "missing_sources": missing_sources,
        "configuration_fingerprint": configuration_fingerprint,
        "retention_policy_version": "daily30-monthly12-v1",
        "paper_backup_ready": status == "complete",
    }
    digest = operations_hash(identity)
    return BackupManifest(
        backup_id="local-backup:" + digest.removeprefix("sha256:"),
        reason=reason,
        logical_date=logical_date,
        created_at=created_at,
        status=status,
        files=files,
        missing_sources=missing_sources,
        configuration_fingerprint=configuration_fingerprint,
        paper_backup_ready=status == "complete",
        content_hash=digest,
    )


def backup_manifest_identity(value: BackupManifest) -> dict[str, object]:
    return {
        "reason": value.reason,
        "logical_date": value.logical_date,
        "created_at": value.created_at,
        "status": value.status,
        "files": [item.model_dump(mode="json") for item in value.files],
        "missing_sources": value.missing_sources,
        "configuration_fingerprint": value.configuration_fingerprint,
        "retention_policy_version": value.retention_policy_version,
        "paper_backup_ready": value.paper_backup_ready,
    }


def _backup_sqlite(source: Path, target: Path) -> None:
    with (
        sqlite3.connect(source) as source_connection,
        sqlite3.connect(target) as target_connection,
    ):
        source_connection.backup(target_connection)
    with sqlite3.connect(f"file:{target}?mode=ro", uri=True) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite 备份完整性检查失败")


def _backup_file(
    logical_name: str,
    kind: Literal["sqlite", "pointer"],
    relative: Path,
    target: Path,
) -> BackupFile:
    payload = target.read_bytes()
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return BackupFile(
        logical_name=logical_name,
        kind=kind,
        relative_path=relative.as_posix(),
        size_bytes=len(payload),
        content_hash=digest,
    )


def _backup_records(namespace: Path) -> list[tuple[Path, BackupManifest]]:
    records = []
    for path in sorted((namespace / "daily").glob("*/*/manifest.json")):
        records.append(
            (
                path.parent,
                BackupManifest.model_validate_json(path.read_text(encoding="utf-8")),
            )
        )
    return records


def _validate_external_root(repository_root: Path, backup_root: Path) -> None:
    if backup_root == repository_root or repository_root in backup_root.parents:
        raise ValueError("ASTRAMIND_BACKUP_DIR 必须位于仓库和 var/ 之外")
    if backup_root == repository_root / "var" or repository_root / "var" in backup_root.parents:
        raise ValueError("ASTRAMIND_BACKUP_DIR 不能位于 var/ 内")


def _safe_remove_backup(path: Path, namespace: Path) -> None:
    resolved = path.resolve()
    if namespace.resolve() not in resolved.parents or not (resolved / "manifest.json").is_file():
        raise ValueError("拒绝删除未解析的备份目录")
    shutil.rmtree(resolved)
    with suppress(OSError):
        resolved.parent.rmdir()


__all__ = [
    "BackupReason",
    "LocalBackupService",
    "backup_manifest_identity",
    "configuration_fingerprint",
    "retained_backup_ids",
]
