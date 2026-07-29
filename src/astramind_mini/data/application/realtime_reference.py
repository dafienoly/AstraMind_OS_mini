"""Load current point-in-time stock universe and L1 industry membership."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb


@dataclass(frozen=True, slots=True)
class RealtimeReference:
    universe: frozenset[str]
    industries: dict[str, str]
    names: dict[str, str]
    instrument_types: dict[str, str]
    price_limits: dict[str, tuple[float, float]]


def load_realtime_reference(
    data_root: Path,
    *,
    as_of: date,
) -> tuple[frozenset[str], dict[str, str]]:
    security = _artifact(data_root, "security_master")
    membership = _artifact(data_root, "industry_membership")
    with duckdb.connect(":memory:") as connection:
        securities = connection.execute(
            "SELECT instrument_id FROM read_parquet(?) WHERE list_status = 'L'",
            [str(security)],
        ).fetchall()
        memberships = connection.execute(
            """
            SELECT instrument_id, industry_code
            FROM read_parquet(?)
            WHERE level = 'L1'
              AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to > ?)
            QUALIFY row_number() OVER (
              PARTITION BY instrument_id ORDER BY effective_from DESC, industry_code
            ) = 1
            """,
            [str(membership), as_of, as_of],
        ).fetchall()
    universe = frozenset(str(row[0]) for row in securities)
    industries = {
        str(instrument): str(industry)
        for instrument, industry in memberships
        if str(instrument) in universe
    }
    return universe, industries


def load_realtime_instrument_reference(
    data_root: Path,
    *,
    as_of: date,
) -> RealtimeReference:
    universe, industries = load_realtime_reference(data_root, as_of=as_of)
    security = _artifact(data_root, "security_master")
    etf = _artifact(data_root, "etf_master")
    limits = _artifacts(data_root, "price_limit", suffix=f"{as_of.year}.parquet")
    with duckdb.connect(":memory:") as connection:
        names = {
            str(instrument): str(name)
            for instrument, name in connection.execute(
                "SELECT instrument_id, name FROM read_parquet(?)",
                [str(security)],
            ).fetchall()
        }
        etf_codes = {
            str(row[0])
            for row in connection.execute(
                "SELECT instrument_id FROM read_parquet(?)",
                [str(etf)],
            ).fetchall()
        }
        price_limits: dict[str, tuple[float, float]] = {}
        if limits:
            price_limits = {
                str(instrument): (float(upper), float(lower))
                for instrument, upper, lower in connection.execute(
                    """
                    SELECT instrument_id, upper_limit, lower_limit
                    FROM read_parquet(?)
                    WHERE trade_date = ? AND limit_prices_usable
                    """,
                    [[str(path) for path in limits], as_of],
                ).fetchall()
            }
    instrument_types = {
        instrument: (
            "etf"
            if instrument in etf_codes
            else (
                "index"
                if instrument.startswith(("000", "399")) and instrument not in universe
                else ("stock" if instrument in universe else "other")
            )
        )
        for instrument in names.keys() | etf_codes
    }
    instrument_types.update(
        {
            code: "index"
            for code in (
                "000001.SH",
                "399001.SZ",
                "399006.SZ",
                "000688.SH",
                "000300.SH",
                "000852.SH",
            )
        }
    )
    return RealtimeReference(
        universe=universe,
        industries=industries,
        names=names,
        instrument_types=instrument_types,
        price_limits=price_limits,
    )


def _artifact(data_root: Path, dataset: str) -> Path:
    artifacts = _artifacts(data_root, dataset, suffix=".parquet")
    if len(artifacts) != 1:
        raise ValueError(f"{dataset} 制品清单无效")
    return artifacts[0]


def _artifacts(data_root: Path, dataset: str, *, suffix: str) -> tuple[Path, ...]:
    pointer = json.loads((data_root / "current" / f"{dataset}.json").read_text(encoding="utf-8"))
    relative = Path(str(pointer["manifest_path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("实时引用数据集指针无效")
    manifest = json.loads((data_root / relative).read_text(encoding="utf-8"))
    artifacts = manifest.get("artifact_paths")
    if not isinstance(artifacts, list):
        raise ValueError(f"{dataset} 制品清单无效")
    result = []
    for value in artifacts:
        artifact = Path(str(value))
        if artifact.is_absolute() or ".." in artifact.parts:
            raise ValueError(f"{dataset} 制品路径无效")
        if artifact.name.endswith(suffix):
            result.append(data_root / relative.parent / artifact)
    return tuple(result)


__all__ = [
    "RealtimeReference",
    "load_realtime_instrument_reference",
    "load_realtime_reference",
]
