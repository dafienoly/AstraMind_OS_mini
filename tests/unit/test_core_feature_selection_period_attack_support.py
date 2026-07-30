"""Fully rehashed joint-definition and period-projection attacks."""

from __future__ import annotations

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_selection import (
    CoreFrozenJointFeatureDefinition,
    CorePeriodJointMatrixProjection,
)


def representative_attack(
    definition: CoreFrozenJointFeatureDefinition,
) -> CoreFrozenJointFeatureDefinition:
    data = definition.model_dump()
    cluster = next(item for item in data["clusters"] if len(item["members"]) > 1)
    replacement = next(item for item in cluster["members"] if item != cluster["representative"])
    data["clusters"] = tuple(
        {**item, "representative": replacement} if item == cluster else item
        for item in data["clusters"]
    )
    representatives = {item["representative"] for item in data["clusters"]}
    selected = tuple(
        item for item in data["candidate_parents"] if item["feature_key"] in representatives
    )
    data["selected_parents"] = selected
    data["model_columns"] = _joint_columns(selected)
    data["model_input_dimension"] = len(data["model_columns"])
    return rehash_definition(data)


def rehash_definition(
    data: dict[str, object],
) -> CoreFrozenJointFeatureDefinition:
    body = {
        key: value for key, value in data.items() if key not in {"definition_id", "content_hash"}
    }
    content_hash = research_hash({"schema": "core-frozen-joint-definition-v1", **body})
    data["definition_id"] = f"core-frozen-joint-definition:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return CoreFrozenJointFeatureDefinition.model_validate(data)


def rehash_projection(data: dict[str, object]) -> CorePeriodJointMatrixProjection:
    body = {
        key: value for key, value in data.items() if key not in {"projection_id", "content_hash"}
    }
    content_hash = research_hash({"schema": "core-period-joint-matrix-v1", **body})
    data["projection_id"] = f"core-period-joint-matrix:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return CorePeriodJointMatrixProjection.model_validate(data)


def _joint_columns(
    parents: tuple[dict[str, object], ...],
) -> tuple[str, ...]:
    return tuple(
        column
        for item in parents
        for column in (
            f"{item['feature_id']}__value",
            f"{item['feature_id']}__is_missing",
            f"{item['feature_id']}__is_not_applicable",
        )
    )


__all__ = ["rehash_projection", "representative_attack"]
