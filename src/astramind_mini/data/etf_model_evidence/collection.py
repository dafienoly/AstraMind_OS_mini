"""Collect official ETF benchmark, NAV, and index history with raw preservation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import RawRecordEnvelope
from astramind_mini.data.etf_foundation.registry import ETF_CODES
from astramind_mini.data.ports import (
    HistoricalMarketDataProvider,
    ProviderTable,
    RawRecordStore,
)

from .contracts import (
    EtfNavObservation,
    EtfOfficialBenchmarkObservation,
    OfficialIndexDailyObservation,
)
from .normalization import (
    MARKET_MODEL_BENCHMARK,
    normalize_nav,
    normalize_official_benchmarks,
    normalize_official_index_daily,
)

BENCHMARK_FIELDS = (
    "ts_code",
    "csname",
    "index_code",
    "index_name",
    "list_status",
    "exchange",
)
NAV_FIELDS = (
    "ts_code",
    "ann_date",
    "nav_date",
    "unit_nav",
    "accum_nav",
    "adj_nav",
)
INDEX_DAILY_FIELDS = (
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
)


@dataclass(frozen=True, slots=True)
class EtfOfficialEvidenceCollection:
    benchmarks: tuple[EtfOfficialBenchmarkObservation, ...]
    nav: tuple[EtfNavObservation, ...]
    index_daily: tuple[OfficialIndexDailyObservation, ...]
    retrieved_at: datetime


class EtfOfficialEvidenceCollector:
    def __init__(
        self,
        *,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
    ) -> None:
        self._provider = provider
        self._raw = raw_store

    async def collect(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> EtfOfficialEvidenceCollection:
        if start_date > end_date:
            raise ValueError("ETF 官方证据开始日期不能晚于结束日期")
        benchmark_table = await self._provider.query(
            "etf_basic",
            params={"list_status": "L"},
            fields=BENCHMARK_FIELDS,
        )
        self._preserve(benchmark_table)
        benchmarks = normalize_official_benchmarks(benchmark_table)
        nav, nav_retrieved = await self._collect_nav(start_date, end_date)
        benchmark_codes = frozenset(
            {row.benchmark_code for row in benchmarks} | {MARKET_MODEL_BENCHMARK}
        )
        index_daily, index_retrieved = await self._collect_indexes(
            benchmark_codes,
            start_date,
            end_date,
        )
        self._validate(benchmarks, nav, index_daily, benchmark_codes, end_date)
        return EtfOfficialEvidenceCollection(
            benchmarks=benchmarks,
            nav=nav,
            index_daily=index_daily,
            retrieved_at=max(benchmark_table.received_at, nav_retrieved, index_retrieved),
        )

    async def _collect_nav(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[tuple[EtfNavObservation, ...], datetime]:
        rows: list[EtfNavObservation] = []
        retrieved: datetime | None = None
        for code in ETF_CODES:
            table = await self._provider.query(
                "fund_nav",
                params={
                    "ts_code": code,
                    "start_date": f"{start_date:%Y%m%d}",
                    "end_date": f"{end_date:%Y%m%d}",
                },
                fields=NAV_FIELDS,
            )
            self._preserve(table)
            rows.extend(normalize_nav(table))
            retrieved = (
                table.received_at if retrieved is None else max(retrieved, table.received_at)
            )
        if retrieved is None:
            raise ValueError("ETF NAV 未执行任何请求")
        return tuple(rows), retrieved

    async def _collect_indexes(
        self,
        codes: frozenset[str],
        start_date: date,
        end_date: date,
    ) -> tuple[tuple[OfficialIndexDailyObservation, ...], datetime]:
        rows: list[OfficialIndexDailyObservation] = []
        retrieved: datetime | None = None
        for code in sorted(codes):
            table = await self._provider.query(
                "index_daily",
                params={
                    "ts_code": code,
                    "start_date": f"{start_date:%Y%m%d}",
                    "end_date": f"{end_date:%Y%m%d}",
                },
                fields=INDEX_DAILY_FIELDS,
            )
            self._preserve(table)
            rows.extend(
                normalize_official_index_daily(
                    table,
                    allowed_codes=frozenset({code}),
                )
            )
            retrieved = (
                table.received_at if retrieved is None else max(retrieved, table.received_at)
            )
        if retrieved is None:
            raise ValueError("官方指数日线未执行任何请求")
        return tuple(rows), retrieved

    @staticmethod
    def _validate(
        benchmarks: tuple[EtfOfficialBenchmarkObservation, ...],
        nav: tuple[EtfNavObservation, ...],
        index_daily: tuple[OfficialIndexDailyObservation, ...],
        benchmark_codes: frozenset[str],
        end_date: date,
    ) -> None:
        if {row.instrument_id for row in benchmarks} != set(ETF_CODES):
            raise ValueError("ETF 官方基准覆盖不完整")
        if missing := set(ETF_CODES) - {row.instrument_id for row in nav}:
            raise ValueError("ETF NAV 覆盖不完整：" + ",".join(sorted(missing)))
        if missing := set(benchmark_codes) - {row.index_code for row in index_daily}:
            raise ValueError("官方指数日线覆盖不完整：" + ",".join(sorted(missing)))
        if any(row.nav_date > end_date for row in nav):
            raise ValueError("ETF NAV 包含截止日后记录")
        if any(row.trade_date > end_date for row in index_daily):
            raise ValueError("官方指数日线包含截止日后记录")

    def _preserve(self, table: ProviderTable) -> None:
        envelope = RawRecordEnvelope(
            provider=table.provider_id,
            interface_name=table.api_name,
            source_endpoint=table.source_endpoint,
            request_identity=table.request_identity,
            received_at=table.received_at,
            schema_version="provider-v1",
            content_hash=content_hash(table.raw_body),
        )
        self._raw.append(envelope, table.raw_body)


__all__ = ["EtfOfficialEvidenceCollection", "EtfOfficialEvidenceCollector"]
