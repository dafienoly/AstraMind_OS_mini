"""Dataset manifest construction and deterministic snapshot assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime

from astramind_mini.contracts import DatasetRef, DataSnapshot

from ..contracts import DatasetManifest, DatasetProviderEpoch
from .identity import bytes_hash, content_hash


def build_dataset_manifest(
    *,
    dataset_name: str,
    schema_version: str,
    provider: str,
    source_endpoint: str,
    request_identity: str,
    retrieved_at: datetime,
    market_timezone: str,
    date_range: tuple[date, date],
    universe: Sequence[str],
    primary_key: Sequence[str],
    availability_rule: str,
    units: Sequence[str],
    row_count: int,
    artifacts: Mapping[str, bytes],
    known_gaps: Sequence[str] = (),
    critical_gaps: Sequence[str] = (),
    provider_lineage: Sequence[DatasetProviderEpoch] = (),
) -> DatasetManifest:
    artifact_hashes = {name: bytes_hash(payload) for name, payload in sorted(artifacts.items())}
    return build_dataset_manifest_from_hashes(
        dataset_name=dataset_name,
        schema_version=schema_version,
        provider=provider,
        source_endpoint=source_endpoint,
        request_identity=request_identity,
        retrieved_at=retrieved_at,
        market_timezone=market_timezone,
        date_range=date_range,
        universe=universe,
        primary_key=primary_key,
        availability_rule=availability_rule,
        units=units,
        row_count=row_count,
        artifact_hashes=artifact_hashes,
        known_gaps=known_gaps,
        critical_gaps=critical_gaps,
        provider_lineage=provider_lineage,
    )


def build_dataset_manifest_from_hashes(
    *,
    dataset_name: str,
    schema_version: str,
    provider: str,
    source_endpoint: str,
    request_identity: str,
    retrieved_at: datetime,
    market_timezone: str,
    date_range: tuple[date, date],
    universe: Sequence[str],
    primary_key: Sequence[str],
    availability_rule: str,
    units: Sequence[str],
    row_count: int,
    artifact_hashes: Mapping[str, str],
    known_gaps: Sequence[str] = (),
    critical_gaps: Sequence[str] = (),
    provider_lineage: Sequence[DatasetProviderEpoch] = (),
) -> DatasetManifest:
    ordered_hashes = dict(sorted(artifact_hashes.items()))
    data_hash = content_hash(ordered_hashes)
    artifact_paths = tuple(ordered_hashes)
    ordered_universe = tuple(sorted(universe))
    ordered_primary_key = tuple(primary_key)
    ordered_units = tuple(sorted(units))
    ordered_gaps = tuple(sorted(known_gaps))
    ordered_critical_gaps = tuple(sorted(critical_gaps))
    ordered_provider_lineage = tuple(sorted(provider_lineage, key=lambda item: item.effective_from))
    identity = {
        "dataset_name": dataset_name,
        "schema_version": schema_version,
        "provider": provider,
        "source_endpoint": source_endpoint,
        "request_identity": request_identity,
        "retrieved_at": retrieved_at,
        "market_timezone": market_timezone,
        "date_range": date_range,
        "universe": ordered_universe,
        "primary_key": ordered_primary_key,
        "availability_rule": availability_rule,
        "units": ordered_units,
        "content_hash": data_hash,
        "row_count": row_count,
        "known_gaps": ordered_gaps,
        "critical_gaps": ordered_critical_gaps,
        "artifact_paths": artifact_paths,
        "publish_status": "complete",
    }
    if ordered_provider_lineage:
        identity["provider_lineage"] = [
            item.model_dump(mode="json") for item in ordered_provider_lineage
        ]
    return DatasetManifest(
        dataset_version=content_hash(identity),
        dataset_name=dataset_name,
        schema_version=schema_version,
        provider=provider,
        source_endpoint=source_endpoint,
        request_identity=request_identity,
        retrieved_at=retrieved_at,
        market_timezone=market_timezone,
        date_range=date_range,
        universe=ordered_universe,
        primary_key=ordered_primary_key,
        availability_rule=availability_rule,
        units=ordered_units,
        content_hash=data_hash,
        row_count=row_count,
        known_gaps=ordered_gaps,
        critical_gaps=ordered_critical_gaps,
        provider_lineage=ordered_provider_lineage,
        artifact_paths=artifact_paths,
        publish_status="complete",
    )


class DataSnapshotBuilder:
    """Build a stable thin-waist snapshot from complete dataset manifests."""

    def build(
        self,
        *,
        manifests: Sequence[DatasetManifest],
        as_of: datetime,
        created_at: datetime,
        code_identity: str,
        known_gaps: Sequence[str] = (),
        resolved_gaps: Sequence[str] = (),
    ) -> DataSnapshot:
        if not manifests:
            raise ValueError("DataSnapshot 至少需要一个数据集")
        names = [manifest.dataset_name for manifest in manifests]
        if len(names) != len(set(names)):
            raise ValueError("DataSnapshot 不允许重复数据集")
        critical = [
            f"{manifest.dataset_name}:{gap}"
            for manifest in manifests
            for gap in manifest.critical_gaps
        ]
        if critical:
            raise ValueError("关键数据缺口阻断快照：" + "；".join(sorted(critical)))
        datasets = tuple(
            DatasetRef(
                dataset_name=manifest.dataset_name,
                dataset_version=manifest.dataset_version,
                schema_version=manifest.schema_version,
                content_hash=manifest.content_hash,
            )
            for manifest in sorted(manifests, key=lambda item: item.dataset_name)
        )
        inherited_gaps = {*known_gaps, *(gap for item in manifests for gap in item.known_gaps)}
        ordered_gaps = tuple(sorted(inherited_gaps - set(resolved_gaps)))
        identity = {
            "as_of": as_of,
            "datasets": [item.model_dump(mode="json") for item in datasets],
            "known_gaps": ordered_gaps,
            "code_identity": code_identity,
        }
        return DataSnapshot(
            snapshot_id="snapshot:" + content_hash(identity),
            as_of=as_of,
            datasets=datasets,
            known_gaps=ordered_gaps,
            created_at=created_at,
            code_identity=code_identity,
        )


__all__ = [
    "DataSnapshotBuilder",
    "build_dataset_manifest",
    "build_dataset_manifest_from_hashes",
]
