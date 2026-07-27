"""Read-only import of the legacy AstraMind formal Silver market release."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb


@dataclass(frozen=True, slots=True)
class LegacySilverRelease:
    release_root: Path
    dataset_version: str
    release_content_hash: str
    created_at: datetime

    def dates(self, table: str) -> frozenset[str]:
        return frozenset(
            path.parent.name.split("=", 1)[1]
            for path in (self.release_root / table).glob("trade_date=*/*.parquet")
        )

    def files(self, table: str) -> tuple[Path, ...]:
        return tuple(sorted((self.release_root / table).glob("**/*.parquet")))

    def files_for_year(self, table: str, year: int) -> tuple[Path, ...]:
        return tuple(sorted((self.release_root / table).glob(f"trade_date={year}-*/*.parquet")))


def discover_legacy_release(root: Path, dataset_version: str) -> LegacySilverRelease:
    release_parent = root / "silver" / dataset_version / "releases"
    manifests = tuple(sorted(release_parent.glob("*/market_panel_manifest.json")))
    if len(manifests) != 1:
        raise ValueError(f"旧 Silver 发布清单数量必须为 1，实际为 {len(manifests)}")
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    if manifest.get("publication_status") != "passed_for_formal_research":
        raise ValueError("旧 Silver 发布未通过正式研究状态")
    content_hash = str(manifest.get("release_content_sha256", ""))
    if len(content_hash) != 64:
        raise ValueError("旧 Silver 发布缺少内容身份")
    return LegacySilverRelease(
        release_root=manifests[0].parent,
        dataset_version=str(manifest["dataset_version"]),
        release_content_hash="sha256:" + content_hash,
        created_at=datetime.fromisoformat(str(manifest["created_at"])),
    )


class LegacyAnnualCompactor:
    def compact(
        self,
        *,
        table: str,
        source_files: tuple[Path, ...],
        supplement_files: tuple[Path, ...],
        output: Path,
        imported_at: datetime,
    ) -> tuple[int, int]:
        if table not in {"daily", "adj_factor"}:
            raise ValueError(f"不支持旧数据表：{table}")
        if not source_files and not supplement_files:
            raise ValueError("年度分区没有输入文件")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.unlink(missing_ok=True)
        legacy_sql = _legacy_projection(table)
        parts: list[str] = []
        parameters: list[object] = []
        if source_files:
            parts.append(legacy_sql)
            parameters.extend((imported_at, [str(path) for path in source_files]))
        if supplement_files:
            parts.append("SELECT * FROM read_parquet(?)")
            parameters.append([str(path) for path in supplement_files])
        union = " UNION ALL ".join(parts)
        order = "trade_date, instrument_id"
        output_literal = str(temporary).replace("'", "''")
        with duckdb.connect(":memory:") as connection:
            connection.execute(
                f"COPY (SELECT * FROM ({union}) ORDER BY {order}) "
                f"TO '{output_literal}' (FORMAT PARQUET, COMPRESSION ZSTD)",
                parameters,
            )
            counts = connection.execute(
                "SELECT count(*), count(DISTINCT (instrument_id, trade_date)) FROM read_parquet(?)",
                [str(temporary)],
            ).fetchone()
            assert counts is not None
            row_count, distinct_count = counts
        if row_count != distinct_count:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"{table} 年度分区存在重复主键")
        temporary.replace(output)
        return int(row_count), int(distinct_count)

    def validate_pair(self, daily: Path, factors: Path) -> tuple[int, int]:
        with duckdb.connect(":memory:") as connection:
            invalid_daily_row = connection.execute(
                """
                SELECT count(*) FROM read_parquet(?)
                WHERE low > least(open, close)
                   OR high < greatest(open, close)
                   OR high < low OR volume_lots < 0 OR amount_thousand_cny < 0
                """,
                [str(daily)],
            ).fetchone()
            invalid_factors_row = connection.execute(
                "SELECT count(*) FROM read_parquet(?) WHERE adjustment_factor <= 0",
                [str(factors)],
            ).fetchone()
            missing_factors_row = connection.execute(
                """
                SELECT count(*) FROM read_parquet(?) daily
                ANTI JOIN read_parquet(?) factors
                USING (instrument_id, trade_date)
                """,
                [str(daily), str(factors)],
            ).fetchone()
            factor_only_row = connection.execute(
                """
                SELECT count(*) FROM read_parquet(?) factors
                ANTI JOIN read_parquet(?) daily
                USING (instrument_id, trade_date)
                """,
                [str(factors), str(daily)],
            ).fetchone()
        assert invalid_daily_row is not None
        assert invalid_factors_row is not None
        assert missing_factors_row is not None
        assert factor_only_row is not None
        invalid_daily = invalid_daily_row[0]
        invalid_factors = invalid_factors_row[0]
        missing_factors = missing_factors_row[0]
        factor_only = factor_only_row[0]
        if invalid_daily or invalid_factors or missing_factors:
            raise ValueError(
                "年度分区质量失败："
                f"daily={invalid_daily},factor={invalid_factors},"
                f"missing_factor={missing_factors}"
            )
        return int(missing_factors), int(factor_only)


def _legacy_projection(table: str) -> str:
    common = """
        'tushare' AS provider,
        'legacy-astramind-silver' AS source_endpoint,
        CAST(? AS TIMESTAMPTZ) AS retrieved_at,
        timezone(
            'Asia/Shanghai',
            CAST(trade_date AS TIMESTAMP) + INTERVAL '18 hours'
        ) AS available_at,
        '1.1.0' AS schema_version
    """
    source_hash = """
        'sha256:' || sha256(
            coalesce(_raw_sha256, '') || '|' || ts_code || '|' ||
            CAST(trade_date AS VARCHAR)
        ) AS source_record_hash
    """
    if table == "daily":
        fields = """
            ts_code AS instrument_id,
            trade_date,
            open,
            high,
            low,
            close,
            pre_close AS previous_close,
            change,
            pct_chg AS percent_change,
            vol AS volume_lots,
            amount AS amount_thousand_cny
        """
    else:
        fields = """
            ts_code AS instrument_id,
            trade_date,
            adj_factor AS adjustment_factor
        """
    return f"SELECT {common}, {source_hash}, {fields} FROM read_parquet(?)"


__all__ = [
    "LegacyAnnualCompactor",
    "LegacySilverRelease",
    "discover_legacy_release",
]
