"""Canonical point-in-time selection for F0 company classifications."""

from __future__ import annotations

from .computation_semantics import F0_FINANCIAL_COMPUTATION_SEMANTICS as _SEMANTICS
from .inputs import F0CompanyType, F0InputBundle


def select_company_type(
    bundle: F0InputBundle,
    instrument_id: str,
) -> F0CompanyType:
    """Select the latest authoritative classification without input-order ties."""
    _validate_selection_semantics()
    decision_date = bundle.core_input.decision_date
    visible = [
        item
        for item in bundle.company_classifications
        if item.instrument_id == instrument_id
        and item.effective_from <= decision_date
        and (item.effective_to is None or decision_date <= item.effective_to)
        and item.available_at <= bundle.core_input.cutoff_at
    ]
    if not visible:
        return F0CompanyType.UNKNOWN

    latest_effective_from = max(item.effective_from for item in visible)
    effective_layer = [
        item for item in visible if item.effective_from == latest_effective_from
    ]
    latest_available_at = max(item.available_at for item in effective_layer)
    authoritative = [
        item
        for item in effective_layer
        if item.available_at == latest_available_at
    ]
    selected = authoritative[0]
    if any(item != selected for item in authoritative[1:]):
        raise ValueError(
            "company classifications conflict at the latest selection key"
        )
    return selected.company_type


def _validate_selection_semantics() -> None:
    expected = (
        _SEMANTICS.classification_identity
        == "instrument_id+effective_from+available_at"
        and _SEMANTICS.classification_interval_policy
        == "decision_date_in_closed_effective_interval"
        and _SEMANTICS.classification_selection
        == "maximum_effective_from_then_maximum_available_at"
        and _SEMANTICS.classification_equal_key_policy
        == "identical_record_deduplicates_otherwise_fail_closed"
    )
    if not expected:
        raise RuntimeError("unsupported F0 company classification semantics")


__all__ = ["select_company_type"]
