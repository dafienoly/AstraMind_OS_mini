"""Preserve legacy provider responses unless a routed source already did so."""

from __future__ import annotations

from ..contracts import RawRecordEnvelope
from ..contracts.source import ProviderBatch
from ..ports import ProviderTable, RawRecordStore
from .identity import content_hash


def preserve_provider_batch_raw(
    batch: ProviderBatch,
    raw_store: RawRecordStore,
) -> None:
    envelope = RawRecordEnvelope(
        provider=batch.provider_id,
        interface_name=batch.native_interface,
        source_endpoint=batch.source_endpoint,
        request_identity=batch.request_identity,
        received_at=batch.retrieved_at,
        schema_version="provider-v2",
        content_hash=content_hash(batch.raw_payload),
    )
    raw_store.append(envelope, batch.raw_payload)


def preserve_provider_table_raw(
    table: ProviderTable,
    raw_store: RawRecordStore,
) -> None:
    if table.raw_record_persisted:
        return
    envelope = RawRecordEnvelope(
        provider=table.provider_id,
        interface_name=table.api_name,
        source_endpoint=table.source_endpoint,
        request_identity=table.request_identity,
        received_at=table.received_at,
        schema_version="provider-v1",
        content_hash=content_hash(table.raw_body),
    )
    raw_store.append(envelope, table.raw_body)


__all__ = ["preserve_provider_batch_raw", "preserve_provider_table_raw"]
