"""DuckDB compaction for resumable tactical-event request partitions."""

from __future__ import annotations

from pathlib import Path

import duckdb


class DuckDBEventDatasetCompactor:
    def compact(
        self,
        *,
        source_files: tuple[Path, ...],
        output: Path,
        order_by: tuple[str, ...],
        date_column: str,
        identity_columns: tuple[str, ...] = ("source_record_hash",),
    ) -> dict[str, object]:
        if not source_files:
            raise ValueError("事件年度分区没有请求制品")
        if not identity_columns:
            raise ValueError("事件数据观察身份列不能为空")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".parquet.tmp")
        temporary.unlink(missing_ok=True)
        ordering = ", ".join(f'"{column}"' for column in order_by)
        identity = ", ".join(f'"{column}"' for column in identity_columns)
        target = str(temporary).replace("'", "''")
        with duckdb.connect(":memory:") as connection:
            connection.execute(
                f"""
                COPY (
                  SELECT DISTINCT * FROM read_parquet(?)
                  ORDER BY {ordering}
                ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
                """,
                [[str(path) for path in source_files]],
            )
            row = connection.execute(
                f"""
                SELECT count(*), count(DISTINCT ({identity})),
                       min("{date_column}"), max("{date_column}")
                FROM read_parquet(?)
                """,
                [str(temporary)],
            ).fetchone()
            columns = {
                str(item[0])
                for item in connection.execute(
                    "DESCRIBE SELECT * FROM read_parquet(?)", [str(temporary)]
                ).fetchall()
            }
            null_holder_count = 0
            early_announcement_count = 0
            if "holder_count" in columns:
                null_row = connection.execute(
                    "SELECT count(*) FROM read_parquet(?) WHERE holder_count IS NULL",
                    [str(temporary)],
                ).fetchone()
                assert null_row is not None
                null_holder_count = int(null_row[0])
                early_row = connection.execute(
                    """
                    SELECT count(*) FROM read_parquet(?)
                    WHERE announced_on < reporting_period
                    """,
                    [str(temporary)],
                ).fetchone()
                assert early_row is not None
                early_announcement_count = int(early_row[0])
        assert row is not None
        if row[0] != row[1]:
            temporary.unlink(missing_ok=True)
            raise ValueError("事件数据内容身份重复")
        temporary.replace(output)
        return {
            "rows": int(row[0]),
            "unique_rows": int(row[1]),
            "start_date": row[2].isoformat() if row[2] else None,
            "end_date": row[3].isoformat() if row[3] else None,
            "null_holder_count_rows": null_holder_count,
            "announcement_before_period_rows": early_announcement_count,
        }


__all__ = ["DuckDBEventDatasetCompactor"]
