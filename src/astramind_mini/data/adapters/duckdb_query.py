"""DuckDB queries constrained to one published manifest artifact."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb

from ..contracts import DatasetManifest


class DuckDBSnapshotQuery:
    def __init__(self, root: Path) -> None:
        self._root = root

    def query_parquet(
        self,
        manifest: DatasetManifest,
        artifact_name: str,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> list[tuple[Any, ...]]:
        if artifact_name not in manifest.artifact_paths:
            raise ValueError("文件不属于指定 DatasetManifest")
        if (
            "latest" in artifact_name.lower()
            or any(char in artifact_name for char in "*?[]/\\")
            or not artifact_name.endswith(".parquet")
        ):
            raise ValueError("DuckDB 只允许明确版本的 Parquet 文件名")
        if sql.count("{dataset}") != 1:
            raise ValueError("查询必须且只能包含一个 {dataset} 占位符")
        digest = manifest.dataset_version.rsplit(":", 1)[-1]
        path = self._root / "datasets" / manifest.dataset_name / digest / artifact_name
        if not path.is_file():
            raise FileNotFoundError(path)
        statement = sql.replace("{dataset}", "read_parquet(?)")
        with duckdb.connect(":memory:") as connection:
            result = connection.execute(statement, [str(path), *parameters]).fetchall()
        return [tuple(row) for row in result]

    def query_parquet_set(
        self,
        manifest: DatasetManifest,
        artifact_names: Sequence[str],
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> list[tuple[Any, ...]]:
        if not artifact_names:
            raise ValueError("至少需要一个 Parquet 文件")
        paths = [self._artifact_path(manifest, artifact_name) for artifact_name in artifact_names]
        if sql.count("{dataset}") != 1:
            raise ValueError("查询必须且只能包含一个 {dataset} 占位符")
        statement = sql.replace("{dataset}", "read_parquet(?)")
        with duckdb.connect(":memory:") as connection:
            result = connection.execute(
                statement,
                [[str(path) for path in paths], *parameters],
            ).fetchall()
        return [tuple(row) for row in result]

    def _artifact_path(
        self,
        manifest: DatasetManifest,
        artifact_name: str,
    ) -> Path:
        if artifact_name not in manifest.artifact_paths:
            raise ValueError("文件不属于指定 DatasetManifest")
        if (
            "latest" in artifact_name.lower()
            or any(char in artifact_name for char in "*?[]/\\")
            or not artifact_name.endswith(".parquet")
        ):
            raise ValueError("DuckDB 只允许明确版本的 Parquet 文件名")
        digest = manifest.dataset_version.rsplit(":", 1)[-1]
        path = self._root / "datasets" / manifest.dataset_name / digest / artifact_name
        if not path.is_file():
            raise FileNotFoundError(path)
        return path


__all__ = ["DuckDBSnapshotQuery"]
