import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from astramind_mini.data.adapters import DuckDBParquetEncoder
from astramind_mini.data.application.daily_pipeline_inputs import events_waiting
from astramind_mini.data.application.daily_reference_inputs import (
    prepare_daily_reference_inputs,
)
from astramind_mini.data.application.dataset_schemas import (
    CORPORATE_ACTION_COLUMNS,
    SECURITY_NAME_HISTORY_COLUMNS,
)
from astramind_mini.data.application.datasets import build_dataset_manifest_from_hashes
from astramind_mini.data.application.identity import bytes_hash
from astramind_mini.data.contracts import DatasetManifest, RawRecordEnvelope
from astramind_mini.data.ports import ProviderTable

RECEIVED_AT = datetime(2026, 1, 16, 10, tzinfo=UTC)


class SyntheticReferenceProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        self.calls.append((api_name, dict(params)))
        rows = self._rows(api_name, params)
        return ProviderTable(
            api_name=api_name,
            fields=tuple(fields),
            rows=rows,
            raw_body={"api": api_name, "params": params, "rows": rows},
            request_identity=bytes_hash(f"{api_name}:{params}".encode()),
            received_at=RECEIVED_AT,
            source_endpoint="api.tushare.pro",
        )

    def _rows(self, api_name: str, params: Mapping[str, object]) -> tuple[dict[str, object], ...]:
        if api_name == "stock_basic":
            if params["list_status"] != "L":
                return ()
            return (
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "合成证券",
                    "area": "深圳",
                    "industry": "银行",
                    "market": "主板",
                    "exchange": "SZSE",
                    "curr_type": "CNY",
                    "list_status": "L",
                    "list_date": "19910403",
                    "delist_date": None,
                    "is_hs": "S",
                },
            )
        if api_name == "index_classify":
            level = str(params["level"])
            prefix = "80" if level == "L1" else "85"
            return tuple(
                {
                    "index_code": f"{prefix}{index:04d}.SI",
                    "industry_name": f"{level}行业{index}",
                    "level": level,
                    "industry_code": f"61{index:04d}",
                    "is_pub": "1",
                    "parent_code": f"61{index:04d}" if level == "L2" else None,
                    "src": "SW2021",
                }
                for index in range(1, 32)
            )
        if api_name == "index_member_all":
            code = str(params.get("l1_code") or params.get("l2_code"))
            if params["is_new"] == "Y" and code.endswith("0001.SI"):
                return (
                    {
                        "ts_code": "000001.SZ",
                        "name": "合成证券",
                        "in_date": "20210101",
                        "out_date": None,
                    },
                )
            return ()
        if api_name == "namechange":
            return (
                {
                    "ts_code": "000001.SZ",
                    "name": "ST合成",
                    "start_date": "20260102",
                    "end_date": None,
                    "ann_date": None,
                    "change_reason": "特别处理",
                },
            )
        if api_name == "dividend" and "20260116" in params.values():
            return (
                {
                    "ts_code": "000001.SZ",
                    "end_date": "20251231",
                    "ann_date": "20260116",
                    "div_proc": "预案",
                    "stk_div": 0,
                    "stk_bo_rate": 0,
                    "stk_co_rate": 0,
                    "cash_div": 0.1,
                    "cash_div_tax": 0.09,
                    "record_date": None,
                    "ex_date": None,
                    "pay_date": None,
                    "div_listdate": None,
                    "imp_ann_date": None,
                    "base_date": "20251231",
                    "base_share": 100,
                },
            )
        return ()


class RecordingRawStore:
    def __init__(self) -> None:
        self.count = 0

    def append(self, envelope: RawRecordEnvelope, payload: object) -> Path:
        self.count += 1
        return Path(f"/raw/{envelope.request_identity}")


def _base_manifest(name: str, primary_key: tuple[str, ...]) -> DatasetManifest:
    return build_dataset_manifest_from_hashes(
        dataset_name=name,
        schema_version="1.0.0",
        provider="tushare",
        source_endpoint="legacy",
        request_identity="sha256:" + "1" * 64,
        retrieved_at=RECEIVED_AT,
        market_timezone="Asia/Shanghai",
        date_range=(date(2021, 1, 1), date(2026, 1, 15)),
        universe=("000001.SZ",),
        primary_key=primary_key,
        availability_rule="provider availability",
        units=(),
        row_count=0,
        artifact_hashes={f"{name}.parquet": "sha256:" + "2" * 64},
        known_gaps=(f"current_{name}_not_available",),
    )


def test_event_window_allows_next_morning_recovery(tmp_path: Path) -> None:
    manifests = {"lhb_event": _base_manifest("lhb_event", ("source_record_hash",))}

    assert events_waiting(
        tmp_path,
        manifests,
        datetime(2026, 1, 16, 9, tzinfo=UTC),
        date(2026, 1, 16),
        True,
    )
    assert not events_waiting(
        tmp_path,
        manifests,
        datetime(2026, 1, 17, 0, 30, tzinfo=UTC),
        date(2026, 1, 16),
        True,
    )


def test_daily_reference_inputs_refresh_all_five_datasets_atomically(tmp_path: Path) -> None:
    encoder = DuckDBParquetEncoder()
    empty_action = tmp_path / "base-corporate-action.parquet"
    empty_action.write_bytes(encoder.encode((), CORPORATE_ACTION_COLUMNS))
    empty_names = tmp_path / "base-security-name-history.parquet"
    empty_names.write_bytes(encoder.encode((), SECURITY_NAME_HISTORY_COLUMNS))
    manifests = {
        "security_master": _base_manifest("security_master", ("instrument_id",)),
        "security_name_history": _base_manifest(
            "security_name_history", ("instrument_id", "effective_start_date", "name")
        ),
        "corporate_action": _base_manifest("corporate_action", ("provider_record_hash",)),
        "industry_taxonomy": _base_manifest("industry_taxonomy", ("industry_code",)),
        "industry_membership": _base_manifest(
            "industry_membership",
            ("industry_code", "instrument_id", "effective_from", "effective_to"),
        ),
    }
    provider = SyntheticReferenceProvider()
    raw = RecordingRawStore()
    state: dict[str, object] = {}

    result = asyncio.run(
        prepare_daily_reference_inputs(
            root=tmp_path,
            provider=provider,
            raw_store=raw,
            encoder=encoder,
            manifests=manifests,
            base_paths={
                "corporate_action": (empty_action,),
                "security_name_history": (empty_names,),
            },
            workspace=tmp_path / "run",
            state=state,
            state_path=tmp_path / "run" / "requests.json",
            run_id="daily-pipeline:test",
            target_date=date(2026, 1, 16),
        )
    )

    assert set(result.manifests) == set(manifests)
    assert all(item.schema_version == "1.1.0" for item in result.manifests.values())
    assert all(not item.known_gaps for item in result.manifests.values())
    assert raw.count == len(provider.calls)
    with duckdb.connect(":memory:") as connection:
        assert connection.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [str(result.paths["security_master"])],
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [str(result.paths["security_name_history"])],
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [str(result.paths["corporate_action"])],
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [str(result.paths["industry_taxonomy"])],
        ).fetchone() == (62,)
        assert connection.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [str(result.paths["industry_membership"])],
        ).fetchone() == (2,)
