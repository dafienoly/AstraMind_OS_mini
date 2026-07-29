"""Compose model activations into a Market Regime status projection."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from astramind_mini.strategy_research.public import (
    MarketModelRecipe,
    ModelActivation,
    ModelActivationStore,
    market_model_catalog,
)

from ..contracts.model_status import MarketModelStatusItem, MarketModelStatusProjection
from ..domain.identity import content_hash

DISPLAY_NAMES = {
    "industry_heat": "行业热力",
    "industry_rotation": "相对轮动",
    "industry_lifecycle": "生命周期结构",
    "industry_research_ranking": "行业内研究顺序",
    "etf_rotation": "ETF 轮动",
}


class MarketModelStatusReader:
    def __init__(
        self,
        store: ModelActivationStore,
        *,
        clock: Callable[[], datetime] | None = None,
        integrity_check: Callable[[ModelActivation], None] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(ZoneInfo("Asia/Shanghai")))
        self._integrity_check = integrity_check

    def current(self) -> MarketModelStatusProjection:
        as_of = self._clock()
        models = tuple(self._read_recipe(recipe) for recipe in market_model_catalog())
        identity = {
            "as_of": as_of,
            "models": [item.model_dump(mode="json") for item in models],
            "known_gaps": [],
            "broker_actions_allowed": False,
        }
        return MarketModelStatusProjection(
            status_id=content_hash(identity),
            as_of=as_of,
            models=models,
        )

    def _read_recipe(self, recipe: MarketModelRecipe) -> MarketModelStatusItem:
        try:
            activation = self._store.current(recipe.family)
        except FileNotFoundError:
            return _fallback(recipe, "v2_not_trained")
        except (ValueError, OSError):
            return _fallback(recipe, "v2_activation_invalid")
        if self._integrity_check is not None:
            try:
                self._integrity_check(activation)
            except (FileNotFoundError, ValueError, OSError):
                return _fallback(recipe, "v2_referenced_artifact_invalid")
        return _from_activation(recipe, activation)


def _from_activation(
    recipe: MarketModelRecipe,
    activation: ModelActivation,
) -> MarketModelStatusItem:
    evidence_state = {
        "active_v2": "supported",
        "unvalidated_v2": "unvalidated",
        "fallback_v1": "unsupported",
        "blocked": "blocked",
    }[activation.state]
    return MarketModelStatusItem.model_validate(
        {
            "model_family": recipe.family,
            "display_name": DISPLAY_NAMES[recipe.family],
            "state": activation.state,
            "method_version": activation.active_method_version,
            "fallback_method_version": activation.fallback_method_version,
            "manifest_id": activation.active_manifest_id,
            "evidence_bundle_id": activation.evidence_bundle_id,
            "evidence_state": evidence_state,
            "effective_at": activation.effective_at,
            "reason_codes": activation.reason_codes,
            "broker_actions_allowed": False,
        }
    )


def _fallback(recipe: MarketModelRecipe, reason: str) -> MarketModelStatusItem:
    return MarketModelStatusItem(
        model_family=recipe.family,
        display_name=DISPLAY_NAMES[recipe.family],
        state="fallback_v1",
        method_version=recipe.baseline_method_version,
        fallback_method_version=recipe.baseline_method_version,
        evidence_state="blocked",
        reason_codes=(reason,),
    )


__all__ = ["MarketModelStatusReader"]
