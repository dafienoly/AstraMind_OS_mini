"""Fail-closed policy for converting evidence into a read-only method pointer."""

from __future__ import annotations

from datetime import datetime

from .contracts import MarketModelEvidenceBundle, MarketModelManifest, ModelActivation
from .identity import freeze_activation


def activation_for_evidence(
    *,
    manifest: MarketModelManifest,
    evidence: MarketModelEvidenceBundle,
    effective_at: datetime,
    allow_unvalidated: bool = False,
) -> ModelActivation:
    if evidence.manifest_id != manifest.manifest_id:
        raise ValueError("市场模型证据与清单身份不一致")
    etf_gate_reasons = _etf_gate_reasons(manifest, evidence)
    if evidence.evidence_state == "supported" and not etf_gate_reasons:
        state = "active_v2"
        method = manifest.method_version
        reasons: tuple[str, ...] = ()
    elif evidence.evidence_state == "unvalidated" and allow_unvalidated:
        state = "unvalidated_v2"
        method = manifest.method_version
        reasons = ()
    else:
        state = "fallback_v1"
        method = manifest.baseline_method_version
        reasons = tuple(sorted(set((*_fallback_reasons(evidence), *etf_gate_reasons))))
    return freeze_activation(
        model_family=manifest.model_family,
        active_method_version=method,
        active_manifest_id=(
            manifest.manifest_id if state in {"active_v2", "unvalidated_v2"} else None
        ),
        evidence_bundle_id=(
            evidence.evidence_bundle_id if state in {"active_v2", "unvalidated_v2"} else None
        ),
        state=state,
        fallback_method_version=manifest.baseline_method_version,
        reason_codes=reasons,
        effective_at=effective_at,
    )


def _fallback_reasons(evidence: MarketModelEvidenceBundle) -> tuple[str, ...]:
    reasons = [reason for validation in evidence.validations for reason in validation.reason_codes]
    reasons.extend(reason for gate in evidence.data_gates for reason in gate.reason_codes)
    if not reasons:
        reasons.append(f"evidence_{evidence.evidence_state}")
    return tuple(sorted(set(reasons)))


def _etf_gate_reasons(
    manifest: MarketModelManifest,
    evidence: MarketModelEvidenceBundle,
) -> tuple[str, ...]:
    if manifest.model_family != "etf_rotation":
        return ()
    required = {
        "point_in_time_mapping",
        "official_benchmark",
        "nav_tradability",
        "l1_spread_60d",
    }
    gates = {gate.gate_name: gate for gate in evidence.data_gates}
    reasons = [f"etf_data_gate_missing:{name}" for name in sorted(required - gates.keys())]
    reasons.extend(
        f"etf_data_gate_not_passed:{name}"
        for name in sorted(required & gates.keys())
        if gates[name].status != "pass"
    )
    return tuple(reasons)


__all__ = ["activation_for_evidence"]
