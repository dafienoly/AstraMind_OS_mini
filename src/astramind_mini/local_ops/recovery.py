"""Non-destructive recovery drill into an isolated local directory."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .backup import backup_manifest_identity
from .contracts import BackupManifest, RecoveryDrillReport
from .identity import operations_hash


class LocalRecoveryDrill:
    def __init__(self, *, backup_namespace: Path, drill_root: Path) -> None:
        self._backup_namespace = backup_namespace.resolve()
        self._drill_root = drill_root.resolve()

    def run(
        self,
        *,
        backup_id: str,
        started_at: datetime,
        completed_at: datetime | None = None,
    ) -> RecoveryDrillReport:
        if started_at.tzinfo is None or (completed_at is not None and completed_at.tzinfo is None):
            raise ValueError("恢复演练时间必须带时区")
        if completed_at is not None and completed_at < started_at:
            raise ValueError("恢复演练结束时间不能早于开始时间")
        backup_dir, manifest = self._find_backup(backup_id)
        if operations_hash(backup_manifest_identity(manifest)) != manifest.content_hash:
            raise ValueError("备份清单内容身份校验失败")
        blockers: list[str] = []
        verified = 0
        sqlite_integrity = 0
        shadow_events = 0
        staging = self._drill_root / ".staging" / uuid.uuid4().hex
        staging.mkdir(parents=True, exist_ok=False)
        try:
            for item in manifest.files:
                source = _safe_member(backup_dir, item.relative_path)
                if not source.is_file() or _file_hash(source) != item.content_hash:
                    blockers.append(f"content_mismatch:{item.logical_name}")
                    continue
                if source.stat().st_size != item.size_bytes:
                    blockers.append(f"size_mismatch:{item.logical_name}")
                    continue
                target = staging / item.relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                if _file_hash(target) != item.content_hash:
                    blockers.append(f"restore_copy_mismatch:{item.logical_name}")
                    continue
                verified += 1
                if item.kind == "sqlite":
                    if not _sqlite_healthy(target):
                        blockers.append(f"sqlite_integrity:{item.logical_name}")
                        continue
                    sqlite_integrity += 1
                    if item.logical_name == "shadow":
                        shadow_events = _shadow_event_count(target)
            status: Literal["healthy", "blocked"] = (
                "healthy" if not blockers and manifest.status == "complete" else "blocked"
            )
            if manifest.status != "complete":
                blockers.extend(f"missing_source:{item}" for item in manifest.missing_sources)
            finished_at = completed_at or datetime.now(UTC)
            report = _report(
                manifest=manifest,
                started_at=started_at,
                completed_at=finished_at,
                status=status,
                verified=verified,
                sqlite_integrity=sqlite_integrity,
                shadow_events=shadow_events,
                blockers=tuple(sorted(set(blockers))),
            )
            final = self._drill_root / report.report_id.rsplit(":", 1)[-1]
            (staging / "report.json").write_text(
                report.model_dump_json(indent=2),
                encoding="utf-8",
            )
            if final.exists():
                existing = RecoveryDrillReport.model_validate_json(
                    (final / "report.json").read_text(encoding="utf-8")
                )
                if existing != report:
                    raise ValueError("恢复演练身份发生内容冲突")
                shutil.rmtree(staging)
            else:
                final.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging, final)
            return report
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def _find_backup(self, backup_id: str) -> tuple[Path, BackupManifest]:
        matches = []
        for path in (self._backup_namespace / "daily").glob("*/*/manifest.json"):
            manifest = BackupManifest.model_validate_json(path.read_text(encoding="utf-8"))
            if manifest.backup_id == backup_id:
                matches.append((path.parent, manifest))
        if len(matches) != 1:
            raise KeyError("无法唯一定位备份身份")
        return matches[0]


def _report(
    *,
    manifest: BackupManifest,
    started_at: datetime,
    completed_at: datetime,
    status: Literal["healthy", "blocked"],
    verified: int,
    sqlite_integrity: int,
    shadow_events: int,
    blockers: tuple[str, ...],
) -> RecoveryDrillReport:
    identity = {
        "backup_id": manifest.backup_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": status,
        "verified_file_count": verified,
        "sqlite_integrity_count": sqlite_integrity,
        "shadow_event_count": shadow_events,
        "blocker_codes": blockers,
        "recovery_target_minutes": 30,
        "paper_recovery_ready": status == "healthy" and manifest.paper_backup_ready,
    }
    digest = operations_hash(identity)
    return RecoveryDrillReport.model_validate(
        {
            "report_id": "recovery-drill:" + digest.removeprefix("sha256:"),
            "content_hash": digest,
            **identity,
        }
    )


def _safe_member(root: Path, relative: str) -> Path:
    item = Path(relative)
    if item.is_absolute() or ".." in item.parts:
        raise ValueError("备份清单包含不安全相对路径")
    resolved = (root / item).resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError("备份文件越过备份目录")
    return resolved


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sqlite_healthy(path: Path) -> bool:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0]) == "ok"


def _shadow_event_count(path: Path) -> int:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='shadow_events'"
        ).fetchone()
        if table is None:
            return 0
        return int(connection.execute("SELECT count(*) FROM shadow_events").fetchone()[0])


__all__ = ["LocalRecoveryDrill"]
