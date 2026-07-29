from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.market_regime.adapters.model_status import MarketModelStatusReader
from astramind_mini.strategy_research.market_models.identity import freeze_activation
from astramind_mini.strategy_research.market_models.recipes import recipe_for
from astramind_mini.strategy_research.public import ModelActivationStore

NOW = datetime(2026, 7, 29, 10, 0, tzinfo=UTC)


def reader(root: Path) -> MarketModelStatusReader:
    return MarketModelStatusReader(
        ModelActivationStore(root / "activations"),
        clock=lambda: NOW,
    )


def test_missing_v2_returns_five_explicit_v1_fallbacks(tmp_path: Path) -> None:
    projection = reader(tmp_path).current()

    assert len(projection.models) == 5
    assert {item.state for item in projection.models} == {"fallback_v1"}
    assert all(item.reason_codes == ("v2_not_trained",) for item in projection.models)
    assert all(item.broker_actions_allowed is False for item in projection.models)
    assert projection.broker_actions_allowed is False


def test_one_unvalidated_activation_does_not_change_other_families(tmp_path: Path) -> None:
    recipe = recipe_for("industry_heat")
    activation = freeze_activation(
        model_family=recipe.family,
        active_method_version=recipe.method_version,
        active_manifest_id="manifest:heat",
        evidence_bundle_id="evidence:heat",
        state="unvalidated_v2",
        fallback_method_version=recipe.baseline_method_version,
        effective_at=NOW,
    )
    ModelActivationStore(tmp_path / "activations").publish(activation)

    projection = reader(tmp_path).current()
    heat = next(item for item in projection.models if item.model_family == "industry_heat")

    assert heat.state == "unvalidated_v2"
    assert heat.evidence_state == "unvalidated"
    assert heat.method_version == recipe.method_version
    assert sum(item.state == "fallback_v1" for item in projection.models) == 4


def test_corrupt_activation_pointer_fails_closed_to_v1(tmp_path: Path) -> None:
    recipe = recipe_for("industry_rotation")
    activation = freeze_activation(
        model_family=recipe.family,
        active_method_version=recipe.method_version,
        active_manifest_id="manifest:rotation",
        evidence_bundle_id="evidence:rotation",
        state="unvalidated_v2",
        fallback_method_version=recipe.baseline_method_version,
        effective_at=NOW,
    )
    store = ModelActivationStore(tmp_path / "activations")
    store.publish(activation)
    pointer = tmp_path / "activations" / "current" / "industry_rotation.json"
    pointer.write_text("{}", encoding="utf-8")

    status = next(
        item
        for item in reader(tmp_path).current().models
        if item.model_family == "industry_rotation"
    )

    assert status.state == "fallback_v1"
    assert status.reason_codes == ("v2_activation_invalid",)
    assert status.method_version == recipe.baseline_method_version


def test_invalid_referenced_artifact_fails_closed_to_v1(tmp_path: Path) -> None:
    recipe = recipe_for("industry_heat")
    activation = freeze_activation(
        model_family=recipe.family,
        active_method_version=recipe.method_version,
        active_manifest_id="manifest:heat",
        evidence_bundle_id="evidence:heat",
        state="unvalidated_v2",
        fallback_method_version=recipe.baseline_method_version,
        effective_at=NOW,
    )
    store = ModelActivationStore(tmp_path / "activations")
    store.publish(activation)

    def reject(_: object) -> None:
        raise ValueError("corrupt")

    projection = MarketModelStatusReader(
        store,
        clock=lambda: NOW,
        integrity_check=reject,
    ).current()
    heat = next(item for item in projection.models if item.model_family == "industry_heat")

    assert heat.state == "fallback_v1"
    assert heat.reason_codes == ("v2_referenced_artifact_invalid",)
