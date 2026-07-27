"""Strategy Research-owned public contracts."""

from pydantic import Field

from .base import AwareDatetime, ContentHash, ContractModel, Identifier, Version


class StrategyVersion(ContractModel):
    strategy_version_id: Identifier
    logic_id: Identifier
    parameter_set_hash: ContentHash
    feature_definition_version: Version
    universe_version: Version
    execution_assumption_version: Version
    code_identity: Identifier
    created_at: AwareDatetime


class PredictionBatch(ContractModel):
    prediction_batch_id: Identifier
    strategy_version_id: Identifier
    feature_snapshot_id: Identifier
    as_of: AwareDatetime
    horizon_sessions: int = Field(ge=1)
    content_hash: ContentHash


__all__ = ["PredictionBatch", "StrategyVersion"]
