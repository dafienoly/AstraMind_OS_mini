"""Data-owned public snapshot contracts."""

from pydantic import Field

from .base import AwareDatetime, ContentHash, ContractModel, Identifier, Version


class DatasetRef(ContractModel):
    dataset_name: Identifier
    dataset_version: Identifier
    schema_version: Version
    content_hash: ContentHash


class DataSnapshot(ContractModel):
    snapshot_id: Identifier
    as_of: AwareDatetime
    datasets: tuple[DatasetRef, ...] = Field(min_length=1)
    known_gaps: tuple[str, ...] = ()
    created_at: AwareDatetime
    code_identity: Identifier


class FeatureSnapshot(ContractModel):
    feature_snapshot_id: Identifier
    data_snapshot_id: Identifier
    as_of: AwareDatetime
    definition_version: Version
    content_hash: ContentHash


__all__ = ["DataSnapshot", "DatasetRef", "FeatureSnapshot"]
