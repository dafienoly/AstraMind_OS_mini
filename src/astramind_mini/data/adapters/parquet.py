"""Deterministic Parquet encoding through DuckDB without pandas or PyArrow."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Sequence
from pathlib import Path

import duckdb
from pydantic import BaseModel


class DuckDBParquetEncoder:
    def encode(
        self,
        rows: Sequence[BaseModel],
        columns: Sequence[tuple[str, str]],
    ) -> bytes:
        definitions = ", ".join(f'"{name}" {kind}' for name, kind in columns)
        projections = ", ".join(f'"{name}"' for name, _ in columns)
        json_columns = ", ".join(f"\"{name}\": '{kind}'" for name, kind in columns)
        with tempfile.TemporaryDirectory(prefix="astramind-parquet-") as temporary:
            directory = Path(temporary)
            source = directory / "rows.ndjson"
            path = directory / "data.parquet"
            with duckdb.connect(":memory:") as connection:
                connection.execute(f"CREATE TABLE dataset ({definitions})")
                if rows:
                    source.write_text(
                        "\n".join(
                            json.dumps(
                                row.model_dump(mode="json"),
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                            )
                            for row in rows
                        ),
                        encoding="utf-8",
                    )
                    connection.execute(
                        f"INSERT INTO dataset SELECT {projections} "
                        f"FROM read_json(?, columns={{{json_columns}}})",
                        [str(source)],
                    )
                connection.execute(
                    "COPY (SELECT * FROM dataset) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                    [str(path)],
                )
            return path.read_bytes()


__all__ = ["DuckDBParquetEncoder"]
