"""Verify every referenced object behind a v2 read-only activation."""

from __future__ import annotations

from pathlib import Path

from .artifacts import SkopsArtifactStore
from .contracts import ModelActivation
from .evidence_store import MarketModelEvidenceStore
from .manifest_store import MarketModelManifestStore


class MarketModelIntegrityVerifier:
    def __init__(self, root: Path) -> None:
        self._manifests = MarketModelManifestStore(root)
        self._evidence = MarketModelEvidenceStore(root)
        self._artifacts = SkopsArtifactStore(root)

    def verify(self, activation: ModelActivation) -> None:
        if activation.state not in {"active_v2", "unvalidated_v2"}:
            return
        if activation.active_manifest_id is None or activation.evidence_bundle_id is None:
            raise ValueError("v2 激活缺少引用身份")
        manifest = self._manifests.load(activation.active_manifest_id)
        evidence = self._evidence.load(activation.evidence_bundle_id)
        if manifest.model_family != activation.model_family:
            raise ValueError("v2 激活与模型家族不一致")
        if manifest.method_version != activation.active_method_version:
            raise ValueError("v2 激活与模型方法版本不一致")
        if evidence.manifest_id != manifest.manifest_id:
            raise ValueError("v2 激活证据与模型清单不一致")
        expected_state = "supported" if activation.state == "active_v2" else "unvalidated"
        if evidence.evidence_state != expected_state:
            raise ValueError("v2 激活与证据状态不一致")
        self._artifacts.load(manifest.artifact_hash)


__all__ = ["MarketModelIntegrityVerifier"]
