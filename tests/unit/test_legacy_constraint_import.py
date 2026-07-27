import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
from pydantic import BaseModel

from astramind_mini.data.adapters import LegacyConstraintAnnualCompactor
from astramind_mini.data.application import content_hash, file_hash
from astramind_mini.data.application.constraint_supplements import (
    ConstraintSupplementService,
)
from astramind_mini.data.application.state_files import constraint_year_is_intact
from astramind_mini.data.contracts import RawRecordEnvelope
from astramind_mini.data.ports import ProviderTable


def _write_legacy(path: Path, query: str) -> None:
    path.parent.mkdir(parents=True)
    with duckdb.connect(":memory:") as connection:
        output = str(path).replace("'", "''")
        connection.execute(f"COPY ({query}) TO '{output}' (FORMAT PARQUET)")


def test_constraint_compactor_preserves_sparse_events_and_marks_bad_limits(
    tmp_path: Path,
) -> None:
    common = "'task' _task_id, repeat('a', 64) _raw_sha256, 'legacy-v1' _dataset_version"
    daily = tmp_path / "daily_basic/trade_date=2000-01-04/data.parquet"
    limits = tmp_path / "stk_limit/trade_date=2007-01-04/data.parquet"
    events = tmp_path / "suspend_d/trade_date=2000-01-04/data.parquet"
    _write_legacy(
        daily,
        f"""
        SELECT '000001.SZ' ts_code, DATE '2000-01-04' trade_date,
               10.0 "close", 1.0 turnover_rate, 1.2 turnover_rate_f,
               NULL::DOUBLE volume_ratio, NULL::DOUBLE pe, NULL::DOUBLE pe_ttm,
               2.0 pb, 3.0 ps, 3.1 ps_ttm, NULL::DOUBLE dv_ratio,
               NULL::DOUBLE dv_ttm, 100.0 total_share, 80.0 float_share,
               70.0 free_share, 1000.0 total_mv, 800.0 circ_mv, {common}
        """,
    )
    _write_legacy(
        limits,
        f"""
        SELECT DATE '2007-01-04' trade_date, '000001.SZ' ts_code,
               NULL::DOUBLE pre_close, 0.0 up_limit, 0.0 down_limit, {common}
        """,
    )
    _write_legacy(
        events,
        f"""
        SELECT '000001.SZ' ts_code, DATE '2000-01-04' trade_date,
               NULL::VARCHAR suspend_timing, 'S' suspend_type, {common}
        UNION ALL
        SELECT '000001.SZ', DATE '2000-01-04', NULL::VARCHAR, 'R', {common}
        """,
    )
    compactor = LegacyConstraintAnnualCompactor()
    imported_at = datetime(2026, 1, 2, tzinfo=UTC)
    outputs = {
        "daily_basic": tmp_path / "out/daily.parquet",
        "stk_limit": tmp_path / "out/limit.parquet",
        "suspend_d": tmp_path / "out/events.parquet",
    }
    sources = {
        "daily_basic": daily,
        "stk_limit": limits,
        "suspend_d": events,
    }
    for table, output in outputs.items():
        compactor.compact(
            table=table,
            source_files=(sources[table],),
            supplement_files=(),
            output=output,
            imported_at=imported_at,
        )

    assert compactor.validate("daily_basic", outputs["daily_basic"]) == {"invalid_rows": 0}
    assert compactor.validate("stk_limit", outputs["stk_limit"]) == {"unusable_limit_rows": 1}
    assert compactor.validate("suspend_d", outputs["suspend_d"]) == {"timed_event_rows": 0}
    with duckdb.connect(":memory:") as connection:
        event_types = connection.execute(
            "SELECT suspension_type FROM read_parquet(?) ORDER BY suspension_type",
            [str(outputs["suspend_d"])],
        ).fetchall()
        availability = connection.execute(
            "SELECT available_at FROM read_parquet(?)",
            [str(outputs["stk_limit"])],
        ).fetchone()
    assert event_types == [("R",), ("S",)]
    assert availability is not None
    assert availability[0].isoformat() == "2007-01-04T08:40:00+08:00"

    state: dict[str, object] = {
        "daily_basic_path": str(outputs["daily_basic"]),
        "daily_basic_hash": file_hash(outputs["daily_basic"]),
        "price_limit_path": str(outputs["stk_limit"]),
        "price_limit_hash": file_hash(outputs["stk_limit"]),
        "suspension_event_path": str(outputs["suspend_d"]),
        "suspension_event_hash": file_hash(outputs["suspend_d"]),
    }
    assert constraint_year_is_intact(state, require_price_limit=True)


class _LargeLimitProvider:
    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        rows: tuple[dict[str, object], ...] = ()
        if api_name == "stk_limit":
            rows = tuple(
                {
                    "trade_date": "20260715",
                    "ts_code": f"{index:06d}.SZ",
                    "pre_close": 10.0,
                    "up_limit": 11.0,
                    "down_limit": 9.0,
                }
                for index in range(5801)
            )
        body = {"code": 0, "data": {"fields": list(fields), "items": rows}}
        return ProviderTable(
            api_name=api_name,
            fields=tuple(fields),
            rows=rows,
            raw_body=body,
            request_identity=content_hash({"api": api_name, "params": dict(params)}),
            received_at=datetime(2026, 7, 27, tzinfo=UTC),
            source_endpoint="synthetic.tushare.local",
        )


class _RawSink:
    def append(self, envelope: RawRecordEnvelope, payload: object) -> Path:
        return Path(envelope.interface_name)


class _Encoder:
    def encode(
        self,
        rows: Sequence[BaseModel],
        columns: Sequence[tuple[str, str]],
    ) -> bytes:
        return f"{len(rows)}:{len(columns)}".encode()


def test_supplement_accepts_gateway_rows_above_public_limit_and_empty_events(
    tmp_path: Path,
) -> None:
    state: dict[str, object] = {"supplements": {}}
    state_path = tmp_path / "state.json"
    service = ConstraintSupplementService(
        provider=_LargeLimitProvider(),
        raw_store=_RawSink(),
        encoder=_Encoder(),
    )

    asyncio.run(
        service.prepare(
            staging=tmp_path,
            state=state,
            state_path=state_path,
            missing={
                "daily_basic": frozenset(),
                "stk_limit": frozenset({date(2026, 7, 15)}),
                "suspend_d": frozenset({date(2000, 1, 12)}),
            },
        )
    )

    supplements = state["supplements"]
    assert isinstance(supplements, dict)
    assert supplements["stk_limit"]["2026-07-15"]["rows"] == 5801
    assert supplements["suspend_d"]["2000-01-12"]["rows"] == 0
