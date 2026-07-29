"""Versioned source-route policy and append-only selection evidence."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from ..contracts.source import (
    DatasetSourceRoute,
    SourceProviderEpoch,
    SourceSelectionEvidence,
)
from .identity import canonical_json, content_hash

DEFAULT_ROUTE_VERSION = "dataset-source-routes-v3"
MINIQMT_COST_OVERRIDE_DATASETS = frozenset({"daily_market", "broad_index_daily"})
MARKET_REQUIRED_FIELDS = (
    "instrument_id",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "previous_close",
    "volume",
    "amount",
)
DEFAULT_DATASETS = (
    "trade_calendar",
    "daily_market",
    "broad_index_daily",
    "industry_index_daily",
    "security_master",
    "security_name_history",
    "corporate_action",
    "adjustment_factor",
    "daily_basic",
    "price_limit",
    "suspension_event",
    "lhb_event",
    "lhb_seat",
    "shareholder_count",
    "industry_taxonomy",
    "industry_membership",
)


class SourceRoutePolicyStore:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root / "source-routes"

    def load(self) -> tuple[DatasetSourceRoute, ...]:
        pointer = self._root / "current.json"
        if not pointer.is_file():
            return default_routes()
        value = json.loads(pointer.read_text(encoding="utf-8"))
        policy_hash = str(value["policy_hash"])
        path = self._root / "policies" / policy_hash.rsplit(":", 1)[-1] / "routes.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_routes = payload["routes"]
        if not isinstance(raw_routes, list) or content_hash(raw_routes) != policy_hash:
            raise ValueError("数据源路由策略内容身份冲突")
        routes = tuple(DatasetSourceRoute.model_validate(item, strict=False) for item in raw_routes)
        return routes

    def publish(
        self,
        routes: tuple[DatasetSourceRoute, ...],
        *,
        gate_evidence: dict[str, str],
        production_scope: bool = False,
    ) -> str:
        miniqmt_routes = {route.dataset_name for route in routes if route.providers[0] == "miniqmt"}
        missing = miniqmt_routes - gate_evidence.keys()
        if missing:
            raise ValueError("MiniQMT 主源缺少质量门禁证据：" + ",".join(sorted(missing)))
        if miniqmt_routes and not production_scope:
            raise ValueError("MiniQMT 主源只能由完整生产范围门禁激活")
        policy_hash = content_hash([item.model_dump(mode="json") for item in routes])
        directory = self._root / "policies" / policy_hash.rsplit(":", 1)[-1]
        payload = {
            "policy_hash": policy_hash,
            "policy_version": DEFAULT_ROUTE_VERSION,
            "published_at": datetime.now(UTC).isoformat(),
            "gate_evidence": gate_evidence,
            "production_scope": production_scope,
            "routes": [item.model_dump(mode="json") for item in routes],
        }
        policy_path = directory / "routes.json"
        if policy_path.is_file():
            existing = json.loads(policy_path.read_text(encoding="utf-8"))
            comparable = (
                "policy_hash",
                "policy_version",
                "gate_evidence",
                "production_scope",
                "routes",
            )
            if any(existing.get(key) != payload.get(key) for key in comparable):
                raise ValueError("数据源策略不可变身份冲突")
        else:
            _write_once(policy_path, canonical_json(payload))
        _atomic_write(
            self._root / "current.json",
            canonical_json({"policy_hash": policy_hash}),
        )
        return policy_hash

    def append_selection(self, evidence: SourceSelectionEvidence) -> Path:
        day = evidence.recorded_at.date().isoformat()
        digest = content_hash(evidence.model_dump(mode="json")).rsplit(":", 1)[-1]
        path = self._root / "selections" / day / f"{digest}.json"
        _write_once(path, canonical_json(evidence.model_dump(mode="json")))
        return path


def default_routes() -> tuple[DatasetSourceRoute, ...]:
    return tuple(
        DatasetSourceRoute(
            dataset_name=name,
            providers=("miniqmt", "tushare")
            if name in MINIQMT_COST_OVERRIDE_DATASETS
            else ("tushare",),
            adapter_version=DEFAULT_ROUTE_VERSION,
            quality_gate_version="user-cost-override-20260729"
            if name in MINIQMT_COST_OVERRIDE_DATASETS
            else "not-promoted",
            timeout_seconds=120,
            required_fields=MARKET_REQUIRED_FIELDS
            if name in MINIQMT_COST_OVERRIDE_DATASETS
            else (),
            primary_key=("instrument_id", "trade_date")
            if name in MINIQMT_COST_OVERRIDE_DATASETS
            else (),
            provider_lineage=(
                (
                    SourceProviderEpoch(
                        provider="tushare",
                        effective_from=date.min,
                        effective_to=date(2026, 7, 28),
                    ),
                    SourceProviderEpoch(
                        provider="miniqmt",
                        effective_from=date(2026, 7, 29),
                    ),
                )
                if name in MINIQMT_COST_OVERRIDE_DATASETS
                else ()
            ),
            allow_empty=name
            in {
                "industry_index_daily",
                "security_name_history",
                "corporate_action",
                "suspension_event",
                "lhb_event",
                "lhb_seat",
                "shareholder_count",
                "industry_membership",
            },
        )
        for name in DEFAULT_DATASETS
    )


def _write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f"数据源策略不可变身份冲突：{path.name}") from None


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["SourceRoutePolicyStore", "default_routes"]
