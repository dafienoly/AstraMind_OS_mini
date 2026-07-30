"""Explicit data-capability gates that participate in Alpha101 output identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

L3_CAPABILITY_STATUS = "unavailable"
L3_CAPABILITY_VERSION = "sw2021-l3-unavailable-until-data-wp-v1"
L3_CAPABILITY_MANIFEST_VERSION = "formulaic-alpha101-industry-capability-v1"


def alpha101_l3_capability_manifest() -> dict[str, object]:
    return {
        "manifest_version": L3_CAPABILITY_MANIFEST_VERSION,
        "taxonomy": "SW2021",
        "level": "L3",
        "status": L3_CAPABILITY_STATUS,
        "capability_version": L3_CAPABILITY_VERSION,
        "activation_rule": "new-versioned-data-work-package-required",
        "string_presence_enables_capability": False,
    }


def canonical_l3_capability_manifest_hash(manifest: Mapping[str, object]) -> str:
    encoded = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


L3_CAPABILITY_MANIFEST_HASH = canonical_l3_capability_manifest_hash(
    alpha101_l3_capability_manifest()
)
EXPECTED_L3_CAPABILITY_MANIFEST_HASH = (
    "sha256:afce84df4dfc634b6b93fc371f5f68dc238dd921c3fc05f6a09f3964cf572c73"
)
if L3_CAPABILITY_MANIFEST_HASH != EXPECTED_L3_CAPABILITY_MANIFEST_HASH:
    raise ValueError("Alpha101 L3 capability changed without a new versioned data work package")


__all__ = [
    "EXPECTED_L3_CAPABILITY_MANIFEST_HASH",
    "L3_CAPABILITY_MANIFEST_HASH",
    "L3_CAPABILITY_MANIFEST_VERSION",
    "L3_CAPABILITY_STATUS",
    "L3_CAPABILITY_VERSION",
    "alpha101_l3_capability_manifest",
    "canonical_l3_capability_manifest_hash",
]
