"""Unique parent-aware reconstruction and validation of frozen selections."""

from __future__ import annotations

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

_RECEIPT_ISSUER = object()


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


class ValidatedCoreFeatureSelection:
    """Opaque receipt issued only by a production reconstruction."""

    __slots__ = ("_issuer_guard", "_manifest", "_parents")

    def __setattr__(self, name: str, value: object) -> None:
        if hasattr(self, "_issuer_guard"):
            raise AttributeError("validated selection receipts are immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("validated selection receipts are immutable")

    def __init__(
        self,
        manifest: CoreFeatureSelectionManifest,
        parents: CoreFeatureSelectionParents,
        *,
        _issuer_guard: object | None = None,
    ) -> None:
        if _issuer_guard is not _RECEIPT_ISSUER:
            raise TypeError("validated selection receipts are factory-issued only")
        self._manifest = manifest
        self._parents = parents
        self._issuer_guard = _issuer_guard

    @property
    def manifest(self) -> CoreFeatureSelectionManifest:
        self._assert_authentic()
        return self._manifest

    @property
    def parents(self) -> CoreFeatureSelectionParents:
        self._assert_authentic()
        return self._parents

    def _assert_authentic(self) -> None:
        if self._issuer_guard is not _RECEIPT_ISSUER:
            raise ValueError("selection validation receipt is not authentic")


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


def rebuild_validated_core_feature_selection(
    parents: CoreFeatureSelectionParents,
) -> ValidatedCoreFeatureSelection:
    """Generate a manifest and its opaque receipt through the production selector."""
    return _issue_receipt(rebuild_core_feature_selection(parents), parents)


def validate_core_feature_selection(
    candidate: CoreFeatureSelectionManifest,
    parents: CoreFeatureSelectionParents,
) -> ValidatedCoreFeatureSelection:
    """Reject any candidate differing from a complete production reconstruction."""
    candidate = CoreFeatureSelectionManifest.model_validate(candidate.model_dump())
    expected = rebuild_core_feature_selection(parents)
    if candidate != expected:
        raise ValueError("selection manifest differs from its reconstructed true parents")
    return _issue_receipt(candidate, parents)


def resolve_validated_core_feature_selection(
    selection: CoreFeatureSelectionManifest | ValidatedCoreFeatureSelection,
    parents: CoreFeatureSelectionParents | None = None,
) -> ValidatedCoreFeatureSelection:
    """Validate raw input once, or authenticate an existing receipt in constant time."""
    if isinstance(selection, ValidatedCoreFeatureSelection):
        selection._assert_authentic()
        if parents is not None and selection.parents != parents:
            raise ValueError("selection receipt does not bind the supplied parents")
        return selection
    if parents is None:
        raise ValueError("raw selection manifests require every true parent")
    return validate_core_feature_selection(selection, parents)


def _issue_receipt(
    manifest: CoreFeatureSelectionManifest,
    parents: CoreFeatureSelectionParents,
) -> ValidatedCoreFeatureSelection:
    return ValidatedCoreFeatureSelection(
        manifest,
        parents,
        _issuer_guard=_RECEIPT_ISSUER,
    )


__all__ = [
    "CoreFeatureSelectionParents",
    "ValidatedCoreFeatureSelection",
    "rebuild_core_feature_selection",
    "rebuild_validated_core_feature_selection",
    "resolve_validated_core_feature_selection",
    "validate_core_feature_selection",
]
