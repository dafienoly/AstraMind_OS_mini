"""Unique parent-aware reconstruction and validation of frozen selections."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass

from ..feature_processing import (
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelManifest,
)
from ..labels import CoreForwardReturnLabelBatch, CoreLabelHorizon
from .models import CoreFeatureSelectionManifest, CoreSelectionSpec
from .plan import CoreSelectionFold, CoreSelectionPlan
from .priors import CoreSelectionPriorManifest

_VALIDATED_CANDIDATES: OrderedDict[bytes, str] = OrderedDict()
_VALIDATED_CANDIDATE_MAXSIZE = 32


@dataclass(frozen=True)
class CoreFeatureSelectionParents:
    """Every immutable parent required to reproduce one selection manifest."""

    panel_manifest: CoreProcessedFeaturePanelManifest
    processed_envelopes: tuple[CoreProcessedFeatureEnvelope, ...]
    label_batches: tuple[CoreForwardReturnLabelBatch, ...]
    selection_plan: CoreSelectionPlan
    selection_fold: CoreSelectionFold
    horizon: CoreLabelHorizon
    prior_manifest: CoreSelectionPriorManifest
    selection_spec: CoreSelectionSpec

    @classmethod
    def freeze(
        cls,
        *,
        panel_manifest: CoreProcessedFeaturePanelManifest,
        processed_envelopes: Sequence[CoreProcessedFeatureEnvelope],
        label_batches: Sequence[CoreForwardReturnLabelBatch],
        selection_plan: CoreSelectionPlan,
        selection_fold: CoreSelectionFold,
        horizon: CoreLabelHorizon,
        prior_manifest: CoreSelectionPriorManifest,
        selection_spec: CoreSelectionSpec | None = None,
    ) -> CoreFeatureSelectionParents:
        return cls(
            panel_manifest=panel_manifest,
            processed_envelopes=tuple(processed_envelopes),
            label_batches=tuple(label_batches),
            selection_plan=selection_plan,
            selection_fold=selection_fold,
            horizon=horizon,
            prior_manifest=prior_manifest,
            selection_spec=selection_spec or CoreSelectionSpec(),
        )


def rebuild_core_feature_selection(
    parents: CoreFeatureSelectionParents,
) -> CoreFeatureSelectionManifest:
    """Run the sole production selector over the exact supplied parent objects."""
    from .selector import select_core_features

    return select_core_features(
        panel_manifest=parents.panel_manifest,
        processed_envelopes=parents.processed_envelopes,
        label_batches=parents.label_batches,
        selection_plan=parents.selection_plan,
        fold=parents.selection_fold,
        horizon=parents.horizon,
        prior_manifest=parents.prior_manifest,
        spec=parents.selection_spec,
    )


def validate_core_feature_selection(
    candidate: CoreFeatureSelectionManifest,
    parents: CoreFeatureSelectionParents,
) -> CoreFeatureSelectionManifest:
    """Reject any candidate differing from a complete production reconstruction."""
    if not isinstance(candidate, CoreFeatureSelectionManifest):
        raise TypeError("selection boundaries accept only candidate manifests")
    candidate_json = CoreFeatureSelectionManifest.__pydantic_serializer__.to_json(candidate)
    fingerprint = hashlib.sha256(candidate_json).digest()
    candidate_content_hash = _VALIDATED_CANDIDATES.get(fingerprint)
    if candidate_content_hash is None:
        normalized = CoreFeatureSelectionManifest.model_validate_json(candidate_json)
        candidate_content_hash = normalized.content_hash
        _VALIDATED_CANDIDATES[fingerprint] = candidate_content_hash
        if len(_VALIDATED_CANDIDATES) > _VALIDATED_CANDIDATE_MAXSIZE:
            _VALIDATED_CANDIDATES.popitem(last=False)
    else:
        _VALIDATED_CANDIDATES.move_to_end(fingerprint)
    expected = rebuild_core_feature_selection(parents)
    if candidate_content_hash != expected.content_hash:
        raise ValueError("selection manifest differs from its reconstructed true parents")
    return expected


__all__ = [
    "CoreFeatureSelectionParents",
    "rebuild_core_feature_selection",
    "validate_core_feature_selection",
]
