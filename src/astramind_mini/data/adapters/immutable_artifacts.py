"""Verified, physically independent publication of immutable dataset directories."""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import duckdb

from ..application.identity import canonical_json, content_hash, file_hash
from ..contracts import DatasetManifest


class ImmutableConflictError(RuntimeError):
    """Raised when immutable bytes or declared dataset metadata disagree."""


@dataclass(frozen=True, slots=True)
class _ArtifactInspection:
    hashes: dict[str, str]
    row_count: int | None
    date_range: tuple[date, date] | None


def publish_dataset_directory(
    *,
    directory: Path,
    manifest: DatasetManifest,
    sources: Mapping[str, Path],
) -> Path:
    """Copy, validate, and atomically expose one complete dataset directory."""
    manifest_payload = canonical_json(manifest.model_dump(mode="json"))
    manifest_path = directory / "manifest.json"
    if directory.exists():
        verify_dataset_directory(
            directory,
            manifest,
            require_independent=True,
        )
        if manifest_path.read_bytes() != manifest_payload:
            raise ImmutableConflictError(f"不可变身份内容冲突：{manifest_path.name}")
        return manifest_path
    directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{directory.name}.", dir=directory.parent))
    try:
        staged = {name: temporary / name for name in manifest.artifact_paths}
        for name, source in sources.items():
            _copy_file(source, staged[name])
        _inspect_artifacts(manifest, staged)
        for name, source in sources.items():
            if _inode(source) == _inode(staged[name]):
                raise ImmutableConflictError(f"不可变制品与源文件共享 inode：{name}")
        _write_manifest(temporary / "manifest.json", manifest_payload)
        try:
            os.rename(temporary, directory)
        except OSError as error:
            if error.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                raise
            return publish_dataset_directory(
                directory=directory,
                manifest=manifest,
                sources=sources,
            )
        _fsync_directory(directory.parent)
        return manifest_path
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def verify_dataset_directory(
    directory: Path,
    manifest: DatasetManifest,
    *,
    require_independent: bool,
) -> Path:
    manifest_path = directory / "manifest.json"
    published = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if published != manifest:
        raise ImmutableConflictError(f"数据集清单身份冲突：{manifest.dataset_name}")
    artifacts = {name: directory / name for name in manifest.artifact_paths}
    if any(not path.is_file() for path in artifacts.values()):
        raise ImmutableConflictError(f"不可变制品缺失：{manifest.dataset_name}")
    _inspect_artifacts(manifest, artifacts)
    if require_independent:
        linked = tuple(name for name, path in artifacts.items() if path.stat().st_nlink > 1)
        if linked:
            raise ImmutableConflictError(
                f"不可变制品仍共享 inode：{manifest.dataset_name}:{','.join(linked)}"
            )
    return manifest_path


def inspect_source_artifacts(
    manifest: DatasetManifest,
    sources: Mapping[str, Path],
) -> None:
    """Validate sources before any destination becomes visible."""
    _inspect_artifacts(manifest, sources)


def _inspect_artifacts(
    manifest: DatasetManifest,
    artifacts: Mapping[str, Path],
) -> _ArtifactInspection:
    hashes = {name: file_hash(path) for name, path in sorted(artifacts.items())}
    if content_hash(hashes) != manifest.content_hash:
        raise ImmutableConflictError("制品字节哈希与 DatasetManifest 不一致")
    parquet_paths = tuple(
        path for name, path in sorted(artifacts.items()) if name.endswith(".parquet")
    )
    if not parquet_paths:
        return _ArtifactInspection(hashes=hashes, row_count=None, date_range=None)
    if any(not _has_parquet_magic(path) for path in parquet_paths):
        raise ImmutableConflictError("Parquet 制品格式无效")
    try:
        row_count, date_range = _parquet_inspection(manifest, parquet_paths)
    except duckdb.Error as error:
        raise ImmutableConflictError("Parquet 制品无法读取") from error
    if row_count != manifest.row_count:
        raise ImmutableConflictError(
            f"制品行数与 DatasetManifest 不一致：{row_count}!={manifest.row_count}"
        )
    if date_range is not None and date_range != manifest.date_range:
        raise ImmutableConflictError(
            f"制品日期范围与 DatasetManifest 不一致：{date_range}!={manifest.date_range}"
        )
    return _ArtifactInspection(hashes=hashes, row_count=row_count, date_range=date_range)


def _parquet_inspection(
    manifest: DatasetManifest,
    paths: tuple[Path, ...],
) -> tuple[int, tuple[date, date] | None]:
    with duckdb.connect(":memory:") as connection:
        parquet_paths = [str(path) for path in paths]
        columns = {
            str(row[0])
            for row in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?, union_by_name=true)",
                [parquet_paths],
            ).fetchall()
        }
        missing_keys = tuple(key for key in manifest.primary_key if key not in columns)
        if missing_keys:
            raise ImmutableConflictError("制品缺少清单主键列：" + ",".join(missing_keys))
        key_expression = ", ".join(_quoted_identifier(key) for key in manifest.primary_key)
        row = connection.execute(
            f"SELECT count(*), count(DISTINCT ({key_expression})) "
            "FROM read_parquet(?, union_by_name=true)",
            [parquet_paths],
        ).fetchone()
        assert row is not None
        row_count = int(row[0])
        if int(row[1]) != row_count:
            raise ImmutableConflictError("制品主键不唯一")
        date_column = next(
            (
                key
                for key in manifest.primary_key
                if key
                in {
                    "trade_date",
                    "calendar_date",
                    "market_date",
                    "nav_date",
                    "reporting_period",
                }
            ),
            None,
        )
        if date_column is None or row_count == 0:
            return row_count, None
        quoted_date = _quoted_identifier(date_column)
        dates = connection.execute(
            f"SELECT min({quoted_date}), max({quoted_date}) "
            "FROM read_parquet(?, union_by_name=true)",
            [parquet_paths],
        ).fetchone()
        assert dates is not None
        return row_count, (cast(date, dates[0]), cast(date, dates[1]))


def _copy_file(source: Path, destination: Path) -> None:
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        shutil.copyfileobj(input_stream, output_stream, 1024 * 1024)
        output_stream.flush()
        os.fsync(output_stream.fileno())


def _write_manifest(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _has_parquet_magic(path: Path) -> bool:
    if path.stat().st_size < 8:
        return False
    with path.open("rb") as stream:
        prefix = stream.read(4)
        stream.seek(-4, os.SEEK_END)
        suffix = stream.read(4)
    return prefix == suffix == b"PAR1"


def _quoted_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _inode(path: Path) -> tuple[int, int]:
    value = path.stat()
    return value.st_dev, value.st_ino


__all__ = [
    "ImmutableConflictError",
    "inspect_source_artifacts",
    "publish_dataset_directory",
    "verify_dataset_directory",
]
