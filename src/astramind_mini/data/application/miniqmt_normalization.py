"""Point-in-time normalization for MiniQMT reference and financial batches."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Literal, cast

from ..contracts.extended_observations import (
    CurrentSectorMembershipObservation,
    FinancialFactObservation,
    IndexConstituentWeightObservation,
    InstrumentSnapshotObservation,
    TopHolderObservation,
)
from ..contracts.source import ProviderBatch
from .identity import content_hash

AvailabilityResolver = Callable[[date], datetime]
META_FIELDS = {
    "instrument_id",
    "statement_type",
    "m_timetag",
    "m_anntime",
    "declareDate",
    "endDate",
    "end_date",
    "report_date",
    "ann_date",
}


def normalize_financial_facts(
    batch: ProviderBatch,
    *,
    availability_resolver: AvailabilityResolver,
    field_units: dict[str, tuple[str | None, str]],
) -> tuple[FinancialFactObservation, ...]:
    result = []
    for row in batch.rows:
        report_period = _required_date(
            row.get("report_date")
            or row.get("endDate")
            or row.get("end_date")
            or row.get("m_timetag")
        )
        announced_on = _required_date(
            row.get("declareDate") or row.get("ann_date") or row.get("m_anntime")
        )
        revision = content_hash(row)
        for field, value in row.items():
            if field in META_FIELDS or not isinstance(value, int | float):
                continue
            currency, unit = field_units.get(field, (None, "provider_native_unverified"))
            result.append(
                FinancialFactObservation(
                    provider=batch.provider_id,
                    source_endpoint=batch.source_endpoint,
                    retrieved_at=batch.retrieved_at,
                    available_at=availability_resolver(announced_on),
                    schema_version="1.0.0",
                    source_record_hash=content_hash({"row": row, "field": field}),
                    instrument_id=str(row["instrument_id"]),
                    statement_type=str(row["statement_type"]),
                    report_period=report_period,
                    announced_on=announced_on,
                    revision_identity=revision,
                    field_name=field,
                    numeric_value=float(value),
                    currency=currency,
                    unit=unit,
                )
            )
    return tuple(result)


def normalize_top_holders(
    batch: ProviderBatch,
    *,
    scope: str,
    availability_resolver: AvailabilityResolver,
) -> tuple[TopHolderObservation, ...]:
    if scope not in {"top10", "top10_float"}:
        raise ValueError("十大股东范围无效")
    result = []
    for row in batch.rows:
        report_period = _required_date(row.get("endDate") or row.get("end_date"))
        announced_on = _required_date(
            row.get("declareDate") or row.get("ann_date") or row.get("m_anntime")
        )
        holder_name = _first_text(row, "name", "holderName", "holder_name")
        result.append(
            TopHolderObservation(
                provider=batch.provider_id,
                source_endpoint=batch.source_endpoint,
                retrieved_at=batch.retrieved_at,
                available_at=availability_resolver(announced_on),
                schema_version="1.0.0",
                source_record_hash=content_hash(row),
                instrument_id=str(row["instrument_id"]),
                holder_scope=cast(Literal["top10", "top10_float"], scope),
                report_period=report_period,
                announced_on=announced_on,
                rank=_optional_int(row, "rank", "holderRank"),
                holder_name=holder_name,
                holding_amount=_optional_float(row, "holdNum", "hold_amount", "holdAmount"),
                holding_ratio_percent=_optional_float(
                    row, "holdRatio", "hold_ratio", "holdingRatio"
                ),
                holder_type=_optional_text(row, "holderType", "holder_type"),
                revision_identity=content_hash(row),
            )
        )
    return tuple(result)


def normalize_index_weights(
    batch: ProviderBatch,
) -> tuple[IndexConstituentWeightObservation, ...]:
    observed_on = batch.retrieved_at.date()
    return tuple(
        IndexConstituentWeightObservation(
            provider=batch.provider_id,
            source_endpoint=batch.source_endpoint,
            retrieved_at=batch.retrieved_at,
            available_at=batch.retrieved_at,
            schema_version="1.0.0",
            source_record_hash=content_hash(row),
            index_id=str(row["index_id"]),
            instrument_id=str(row["instrument_id"]),
            observed_on=observed_on,
            weight_percent=_required_float(row.get("weight")),
        )
        for row in batch.rows
    )


def normalize_sector_memberships(
    batch: ProviderBatch,
) -> tuple[CurrentSectorMembershipObservation, ...]:
    observed_on = batch.retrieved_at.date()
    return tuple(
        CurrentSectorMembershipObservation(
            provider=batch.provider_id,
            source_endpoint=batch.source_endpoint,
            retrieved_at=batch.retrieved_at,
            available_at=batch.retrieved_at,
            schema_version="1.0.0",
            source_record_hash=content_hash(row),
            sector_name=str(row["sector_name"]),
            instrument_id=str(row["instrument_id"]),
            observed_on=observed_on,
        )
        for row in batch.rows
    )


def normalize_instrument_snapshots(
    batch: ProviderBatch,
) -> tuple[InstrumentSnapshotObservation, ...]:
    return tuple(
        InstrumentSnapshotObservation(
            provider=batch.provider_id,
            source_endpoint=batch.source_endpoint,
            retrieved_at=batch.retrieved_at,
            available_at=batch.retrieved_at,
            schema_version="1.0.0",
            source_record_hash=content_hash(row),
            instrument_id=str(row["instrument_id"]),
            observed_on=batch.retrieved_at.date(),
            name=_optional_text(row, "InstrumentName", "name"),
            exchange_id=_optional_text(row, "ExchangeID"),
            listed_on=_optional_date(row.get("OpenDate")),
            delisted_on=_optional_date(row.get("ExpireDate")),
            total_shares=_optional_float(row, "TotalVolume"),
            float_shares=_optional_float(row, "FloatVolume"),
            previous_close=_optional_float(row, "PreClose"),
            upper_limit=_optional_float(row, "UpStopPrice"),
            lower_limit=_optional_float(row, "DownStopPrice"),
            is_trading=_optional_bool(row.get("IsTrading")),
            stock_status=_optional_int(row, "StockStatus"),
        )
        for row in batch.rows
    )


def _required_date(value: object) -> date:
    parsed = _optional_date(value)
    if parsed is None:
        raise ValueError("MiniQMT 点时记录缺少报告期或公告日期")
    return parsed


def _required_float(value: object) -> float:
    if not isinstance(value, int | float):
        raise ValueError("MiniQMT 数值字段缺失")
    return float(value)


def _optional_date(value: object) -> date | None:
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(int(value)) if isinstance(value, int | float) else str(value)
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) >= 13:
        return datetime.fromtimestamp(int(digits[:13]) / 1000, tz=UTC).date()
    if len(digits) >= 8:
        return datetime.strptime(digits[:8], "%Y%m%d").date()
    return None


def _first_text(row: dict[str, object], *fields: str) -> str:
    value = _optional_text(row, *fields)
    if value is None:
        raise ValueError("十大股东记录缺少股东名称")
    return value


def _optional_text(row: dict[str, object], *fields: str) -> str | None:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return str(value)
    return None


def _optional_float(row: dict[str, object], *fields: str) -> float | None:
    for field in fields:
        value = row.get(field)
        if isinstance(value, int | float):
            return float(value)
    return None


def _optional_int(row: dict[str, object], *fields: str) -> int | None:
    value = _optional_float(row, *fields)
    return int(value) if value is not None else None


def _optional_bool(value: object) -> bool | None:
    return bool(value) if isinstance(value, bool | int) else None


__all__ = [
    "normalize_financial_facts",
    "normalize_index_weights",
    "normalize_instrument_snapshots",
    "normalize_sector_memberships",
    "normalize_top_holders",
]
