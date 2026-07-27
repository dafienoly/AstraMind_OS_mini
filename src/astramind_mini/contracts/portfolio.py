"""Portfolio & Risk-owned public contracts."""

from enum import StrEnum

from pydantic import Field

from .base import AwareDatetime, ContentHash, ContractModel, Identifier, Version


class Sleeve(StrEnum):
    TACTICAL = "tactical"
    CORE = "core"


class OptimizationProblem(ContractModel):
    optimization_problem_id: Identifier
    prediction_batch_ids: tuple[Identifier, ...] = Field(min_length=1)
    portfolio_state_id: Identifier
    constraints_version: Version
    cost_model_version: Version
    as_of: AwareDatetime
    content_hash: ContentHash


class OptimizationResult(ContractModel):
    optimization_result_id: Identifier
    optimization_problem_id: Identifier
    optimizer_version: Version
    created_at: AwareDatetime
    content_hash: ContentHash


class PortfolioTarget(ContractModel):
    portfolio_target_id: Identifier
    optimization_result_id: Identifier
    sleeve: Sleeve
    as_of: AwareDatetime
    content_hash: ContentHash


__all__ = [
    "OptimizationProblem",
    "OptimizationResult",
    "PortfolioTarget",
    "Sleeve",
]
