"""Fully rehashed selection attacks that remain internally self-consistent."""

from __future__ import annotations

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.feature_selection import (
    CoreFeatureSelectionManifest,
    CoreFeatureSelectionParents,
    CoreSelectionReason,
)


class _LegacyReceiptShape:
    """Test-only model of every forgeable in-process receipt attribute."""

    __slots__ = ("_issuer_guard", "_manifest", "_parents")

    def __init__(
        self,
        manifest: CoreFeatureSelectionManifest,
        parents: CoreFeatureSelectionParents,
    ) -> None:
        self._manifest = manifest
        self._parents = parents
        self._issuer_guard = object()


def forged_bootstrap_p_value(
    selection: CoreFeatureSelectionManifest,
    value: float = 0.01,
) -> CoreFeatureSelectionManifest:
    data = selection.model_dump()
    evidence = list(data["feature_evidence"])
    index = next(
        position for position, item in enumerate(evidence) if item["bootstrap_p_value"] is not None
    )
    evidence[index] = {**evidence[index], "bootstrap_p_value": value}
    data["feature_evidence"] = tuple(evidence)
    return _freeze(data)


def forged_complete_link_split(
    selection: CoreFeatureSelectionManifest,
) -> CoreFeatureSelectionManifest:
    data = selection.model_dump()
    active = list(data["feature_evidence"][:3])
    active_keys = tuple(item["feature_key"] for item in active)
    data["pair_correlations"] = tuple(
        {
            **item,
            "median_daily_spearman": 0.0,
            "distance": 1.0,
        }
        for item in data["pair_correlations"]
    )
    data["clusters"] = tuple(
        {"members": (key,), "representative": key} for key in sorted(active_keys)
    )
    evidence = list(data["feature_evidence"])
    for index in range(3):
        evidence[index] = {
            **evidence[index],
            "reason_code": CoreSelectionReason.SELECTED,
        }
    data["feature_evidence"] = tuple(evidence)
    data["selected_feature_keys"] = active_keys
    data["selected_feature_ids"] = tuple(item["feature_id"] for item in active)
    return _freeze(data)


def forged_cluster_representative(
    selection: CoreFeatureSelectionManifest,
) -> CoreFeatureSelectionManifest:
    data = selection.model_dump()
    cluster = next(item for item in data["clusters"] if len(item["members"]) == 2)
    old_representative = cluster["representative"]
    replacement = next(item for item in cluster["members"] if item != old_representative)
    data["clusters"] = tuple(
        {**item, "representative": replacement} if item == cluster else item
        for item in data["clusters"]
    )
    evidence = list(data["feature_evidence"])
    by_key = {item["feature_key"]: index for index, item in enumerate(evidence)}
    evidence[by_key[old_representative]] = {
        **evidence[by_key[old_representative]],
        "complexity": 999,
        "reason_code": CoreSelectionReason.CLUSTER_REDUNDANT,
    }
    evidence[by_key[replacement]] = {
        **evidence[by_key[replacement]],
        "reason_code": CoreSelectionReason.SELECTED,
    }
    data["feature_evidence"] = tuple(evidence)
    selected_keys = tuple(
        item["feature_key"]
        for item in evidence
        if item["reason_code"] == CoreSelectionReason.SELECTED
    )
    selected_ids = tuple(
        item["feature_id"]
        for item in evidence
        if item["reason_code"] == CoreSelectionReason.SELECTED
    )
    data["selected_feature_keys"] = selected_keys
    data["selected_feature_ids"] = selected_ids
    return _freeze(data)


def forged_turnover(
    selection: CoreFeatureSelectionManifest,
    value: float = 0.5,
) -> CoreFeatureSelectionManifest:
    data = selection.model_dump()
    evidence = list(data["feature_evidence"])
    index = next(position for position, item in enumerate(evidence) if item["turnover"] is not None)
    transitions = tuple(
        {**item, "turnover_ratio": value} if item["valid"] else item
        for item in evidence[index]["turnover_transitions"]
    )
    evidence[index] = {
        **evidence[index],
        "turnover": value,
        "turnover_transitions": transitions,
    }
    data["feature_evidence"] = tuple(evidence)
    return _freeze(data)


def forged_legacy_receipts(
    selection: CoreFeatureSelectionManifest,
    parents: CoreFeatureSelectionParents,
) -> tuple[object, ...]:
    """Build subclass, copied-guard and raw-object forms of the former receipt."""

    class OverrideAuthenticity(_LegacyReceiptShape):
        def _assert_authentic(self) -> None:
            return None

    override = OverrideAuthenticity(selection, parents)
    source = _LegacyReceiptShape(selection, parents)
    copied_guard = object.__new__(_LegacyReceiptShape)
    object.__setattr__(copied_guard, "_manifest", selection)
    object.__setattr__(copied_guard, "_parents", parents)
    object.__setattr__(
        copied_guard,
        "_issuer_guard",
        object.__getattribute__(source, "_issuer_guard"),
    )
    raw_object = object.__new__(_LegacyReceiptShape)
    object.__setattr__(raw_object, "_manifest", selection)
    object.__setattr__(raw_object, "_parents", parents)
    object.__setattr__(raw_object, "_issuer_guard", object())
    return override, copied_guard, raw_object


def _freeze(data: dict[str, object]) -> CoreFeatureSelectionManifest:
    body = {key: value for key, value in data.items() if key not in {"manifest_id", "content_hash"}}
    content_hash = research_hash({"schema": "core-feature-selection-manifest-v1", **body})
    data["manifest_id"] = f"core-selection:{content_hash.removeprefix('sha256:')}"
    data["content_hash"] = content_hash
    return CoreFeatureSelectionManifest.model_validate(data)


__all__ = [
    "forged_bootstrap_p_value",
    "forged_cluster_representative",
    "forged_complete_link_split",
    "forged_legacy_receipts",
    "forged_turnover",
]
