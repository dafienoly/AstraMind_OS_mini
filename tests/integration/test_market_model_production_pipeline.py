from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pytest
from sklearn.ensemble import HistGradientBoostingRegressor  # type: ignore[import-untyped]

from astramind_mini.strategy_research.market_models.evidence_store import (
    MarketModelEvidenceStore,
)
from astramind_mini.strategy_research.market_models.manifest_store import (
    MarketModelManifestStore,
)
from astramind_mini.strategy_research.market_models.production import (
    ProductionFeatureMatrix,
    ProductionMarketModelService,
    ProductionRunResult,
)
from astramind_mini.strategy_research.market_models.production.artifacts import (
    serialize_deterministically,
)
from astramind_mini.strategy_research.market_models.production.contracts import (
    ProductionFamily,
)
from astramind_mini.strategy_research.market_models.production.environment import (
    production_dependency_identity,
)
from astramind_mini.strategy_research.market_models.production.matrix import (
    ProductionFeatureMatrixBuilder,
    point_in_time_samples,
)
from astramind_mini.strategy_research.market_models.production.publisher import (
    _data_gates,
)
from astramind_mini.strategy_research.market_models.production.snapshot import (
    VerifiedSnapshotReader,
)
from astramind_mini.strategy_research.market_models.production.source import (
    REQUIRED_DATASETS,
    ProductionHistoryReader,
)
from astramind_mini.strategy_research.market_models.production.storage import (
    ProductionFeatureMatrixStore,
    ProductionPredictionStore,
)
from astramind_mini.strategy_research.market_models.production.trainer import (
    ProductionTrainedBundle,
)
from astramind_mini.strategy_research.market_models.recipes import recipe_for
from astramind_mini.strategy_research.market_models.splits import (
    build_walk_forward_folds,
    final_training_sample_ids,
)
from tests.integration.production_market_model_fixture import (
    INDUSTRIES,
    PARAMETERS,
    SHANGHAI,
    TRADING_DAYS,
    production_snapshot,
)


def test_stage_one_trains_both_families_idempotently_and_stays_unvalidated(
    tmp_path: Path,
) -> None:
    data_root, snapshot_id, _ = production_snapshot(tmp_path / "input")
    output_root = tmp_path / "output"
    service = ProductionMarketModelService(
        data_root=data_root,
        output_root=output_root,
        parameter_grid=PARAMETERS,
    )
    results: dict[ProductionFamily, ProductionRunResult] = {}
    families: tuple[tuple[ProductionFamily, tuple[int, ...]], ...] = (
        ("industry_heat", (1, 5)),
        ("industry_rotation", (5, 20)),
    )
    for family, horizons in families:
        results[family] = _run_and_assert_family(
            family=family,
            service=service,
            output_root=output_root,
            snapshot_id=snapshot_id,
            horizons=horizons,
        )
    assert not (output_root / "activations").exists()
    _assert_corrupt_artifact_fails_closed(
        service=service,
        output_root=output_root,
        snapshot_id=snapshot_id,
        heat_result=results["industry_heat"],
    )


def _run_and_assert_family(
    family: ProductionFamily,
    *,
    service: ProductionMarketModelService,
    output_root: Path,
    snapshot_id: str,
    horizons: tuple[int, ...],
) -> ProductionRunResult:
    result = service.run(
        model_family=family,
        data_snapshot_id=snapshot_id,
        scheduled_month=date(2024, 1, 1),
        code_identity="test:wp-0062",
    )
    assert result.state == "trained_evidence_insufficient"
    assert result.reason_codes == ("supportive_evidence_not_validated",)
    assert result.broker_actions_allowed is False
    assert result.portfolio_targets_allowed is False
    assert result.order_plans_allowed is False
    matrix = ProductionFeatureMatrixStore(output_root).load(_required(result.feature_matrix_id))
    manifest = MarketModelManifestStore(output_root).load(_required(result.manifest_id))
    evidence = MarketModelEvidenceStore(output_root).load(_required(result.evidence_bundle_id))
    publication = ProductionPredictionStore(output_root).load(
        _required(result.prediction_publication_id)
    )
    assert manifest.data_snapshot_id == snapshot_id
    assert manifest.feature_snapshot_id == matrix.feature_snapshot.feature_snapshot_id
    assert manifest.training_window.start == date(2012, 12, 31)
    assert manifest.training_window.end == date(2022, 12, 31)
    assert manifest.maturity_cutoff == date(2022, 12, 31)
    assert "duckdb" in {item.package for item in manifest.dependency_versions}
    assert publication.batch.evidence_state == "unvalidated"
    assert publication.batch.horizons == horizons
    assert publication.baseline_method_version == recipe_for(family).baseline_method_version
    assert len(publication.batch.regressions) == len(INDUSTRIES) * len(horizons)
    assert publication.broker_actions_allowed is False
    assert publication.portfolio_targets_allowed is False
    assert publication.order_plans_allowed is False
    assert evidence.evidence_state == "unvalidated"
    gates = {item.gate_name: item for item in evidence.data_gates}
    assert gates["supportive_evidence"].status == "pending"
    assert gates["label_maturity"].observation_count == _mature_sample_count(matrix, family)
    assert gates["label_maturity"].coverage_ratio == pytest.approx(
        _mature_sample_count(matrix, family) / _candidate_sample_count(matrix, family)
    )
    _assert_daily_training_semantics(matrix, family)
    files_before = _file_set(output_root)
    assert (
        service.run(
            model_family=family,
            data_snapshot_id=snapshot_id,
            scheduled_month=date(2024, 1, 1),
            code_identity="test:wp-0062",
        )
        == result
    )
    assert _file_set(output_root) == files_before
    return result


def _assert_corrupt_artifact_fails_closed(
    *,
    service: ProductionMarketModelService,
    output_root: Path,
    snapshot_id: str,
    heat_result: ProductionRunResult,
) -> None:
    heat_manifest = MarketModelManifestStore(output_root).load(_required(heat_result.manifest_id))
    artifact = (
        output_root
        / "artifacts"
        / heat_manifest.artifact_hash.removeprefix("sha256:")
        / "model.skops"
    )
    artifact.write_bytes(b"tampered")
    incompatible = service.run(
        model_family="industry_heat",
        data_snapshot_id=snapshot_id,
        scheduled_month=date(2024, 1, 1),
        code_identity="test:wp-0062",
    )
    assert incompatible.state == "artifact_incompatible"
    assert incompatible.reason_codes == ("production_artifact_integrity_failed",)
    assert incompatible.prediction_publication_id is None


def test_missing_dataset_and_unsupported_family_publish_only_accurate_states(
    tmp_path: Path,
) -> None:
    data_root, snapshot_id, _ = production_snapshot(
        tmp_path / "input",
        include_official=False,
    )
    output_root = tmp_path / "output"
    service = ProductionMarketModelService(
        data_root=data_root,
        output_root=output_root,
        parameter_grid=PARAMETERS,
    )
    blocked = service.run(
        model_family="industry_heat",
        data_snapshot_id=snapshot_id,
        scheduled_month=date(2024, 1, 1),
        code_identity="test:wp-0062",
    )
    unavailable = service.run(
        model_family="industry_lifecycle",
        data_snapshot_id=snapshot_id,
        scheduled_month=date(2024, 1, 1),
        code_identity="test:wp-0062",
    )

    assert blocked.state == "training_data_blocked"
    assert blocked.reason_codes == ("missing_dataset:official_index_daily",)
    assert unavailable.state == "production_pipeline_unavailable"
    assert unavailable.reason_codes == ("family_not_in_wp0062_stage_one",)
    assert not (output_root / "predictions").exists()
    assert not (output_root / "artifacts").exists()
    assert not (output_root / "activations").exists()


def test_corrupt_snapshot_artifact_fails_closed_without_prediction(
    tmp_path: Path,
) -> None:
    data_root, snapshot_id, manifests = production_snapshot(tmp_path / "input")
    official = manifests["official_index_daily"]
    artifact = (
        data_root
        / "datasets"
        / official.dataset_name
        / official.dataset_version.removeprefix("sha256:")
        / "data.parquet"
    )
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    output_root = tmp_path / "output"
    result = ProductionMarketModelService(
        data_root=data_root,
        output_root=output_root,
        parameter_grid=PARAMETERS,
    ).run(
        model_family="industry_rotation",
        data_snapshot_id=snapshot_id,
        scheduled_month=date(2024, 1, 1),
        code_identity="test:wp-0062",
    )

    assert result.state == "training_data_blocked"
    assert result.reason_codes == ("immutable_artifact_hash_invalid:official_index_daily",)
    assert not (output_root / "predictions").exists()
    assert not (output_root / "artifacts").exists()


def test_features_exclude_observations_after_decision_time_and_future_schedule(
    tmp_path: Path,
) -> None:
    data_root, snapshot_id, _ = production_snapshot(
        tmp_path / "input",
        late_latest_industry=True,
    )
    verified = VerifiedSnapshotReader(data_root).load(
        snapshot_id,
        required_datasets=REQUIRED_DATASETS,
    )
    history = ProductionHistoryReader().load(verified)

    assert not any(
        bar.industry_code == INDUSTRIES[0][0] and bar.trade_date == TRADING_DAYS[-1]
        for bar in history.industry_bars
    )
    assert any(
        bar.industry_code == INDUSTRIES[1][0] and bar.trade_date == TRADING_DAYS[-1]
        for bar in history.industry_bars
    )

    output_root = tmp_path / "output"
    result = ProductionMarketModelService(
        data_root=data_root,
        output_root=output_root,
        parameter_grid=PARAMETERS,
    ).run(
        model_family="industry_heat",
        data_snapshot_id=snapshot_id,
        scheduled_month=date(2023, 11, 1),
        code_identity="test:wp-0062",
    )
    assert result.state == "training_data_blocked"
    assert result.reason_codes == ("data_snapshot_after_scheduled_month",)
    assert not (output_root / "predictions").exists()


def test_skops_model_bytes_are_reproducible_across_independent_fits() -> None:
    features = np.arange(240, dtype=float).reshape(120, 2)
    labels = np.sin(np.arange(120, dtype=float) / 5.0)

    def fitted() -> dict[str, HistGradientBoostingRegressor]:
        return {
            "5": HistGradientBoostingRegressor(
                random_state=20260729,
                early_stopping=False,
                max_iter=20,
                min_samples_leaf=2,
            ).fit(features, labels)
        }

    first = serialize_deterministically(fitted())
    second = serialize_deterministically(fitted())

    assert first.content_hash == second.content_hash
    assert first.payload == second.payload


def test_production_dependency_identity_includes_duckdb() -> None:
    assert "duckdb" in {package for package, _ in production_dependency_identity()}


def test_data_gate_coverage_counts_missing_feature_cells_and_maturity_denominator(
    tmp_path: Path,
) -> None:
    data_root, snapshot_id, _ = production_snapshot(tmp_path / "input")
    verified = VerifiedSnapshotReader(data_root).load(
        snapshot_id,
        required_datasets=REQUIRED_DATASETS,
    )
    matrix = ProductionFeatureMatrixBuilder().build(
        family="industry_heat",
        data_snapshot_id=snapshot_id,
        history=ProductionHistoryReader().load(verified),
    )
    first = matrix.rows[0]
    missing = first.model_copy(
        update={"features": (None, *first.features[1:])},
    )
    matrix_with_missing = matrix.model_copy(
        update={"rows": (missing, *matrix.rows[1:])},
    )
    trained = ProductionTrainedBundle(
        estimators={},
        parameters={},
        training_start=date(2012, 12, 31),
        training_end=date(2022, 12, 31),
        maturity_cutoff=date(2022, 12, 31),
        mature_sample_count=75,
        label_candidate_sample_count=100,
    )

    gates = {gate.gate_name: gate for gate in _data_gates(matrix_with_missing, trained)}
    total_cells = (len(matrix.rows) + len(matrix.inference_rows)) * len(matrix.feature_names)

    assert gates["production_feature_matrix"].observation_count == total_cells - 1
    assert gates["production_feature_matrix"].coverage_ratio == pytest.approx(
        (total_cells - 1) / total_cells
    )
    assert gates["label_maturity"].coverage_ratio == pytest.approx(0.75)
    no_denominator = {
        gate.gate_name: gate
        for gate in _data_gates(
            matrix_with_missing,
            replace(
                trained,
                mature_sample_count=0,
                label_candidate_sample_count=0,
            ),
        )
    }
    assert no_denominator["label_maturity"].coverage_ratio is None


def _assert_daily_training_semantics(
    matrix: ProductionFeatureMatrix,
    family: ProductionFamily,
) -> None:
    recipe = recipe_for(family)
    calendar = {day: index for index, day in enumerate(TRADING_DAYS)}
    for horizon in recipe.horizons:
        row = next(
            candidate
            for candidate in matrix.rows
            if candidate.entity_id == INDUSTRIES[0][0]
            and candidate.horizon_sessions == horizon
            and candidate.feature_at.date() == date(2021, 1, 4)
        )
        assert calendar[row.label_end_at.date()] - calendar[row.feature_at.date()] == horizon

        samples = point_in_time_samples(matrix, horizon=horizon)
        cutoff = datetime(2022, 12, 31, 18, tzinfo=SHANGHAI)
        folds = build_walk_forward_folds(
            samples,
            recipe=recipe,
            purpose="development",
            evidence_cutoff=cutoff,
        )
        indexed = {sample.sample_id: sample for sample in samples}
        assert len(folds) == 12
        for fold in folds:
            validation = tuple(indexed[sample_id] for sample_id in fold.validation_sample_ids)
            assert len({sample.feature_at.date() for sample in validation}) > 1
            assert max(sample.label_available_at for sample in validation) <= cutoff


def _mature_sample_count(
    matrix: ProductionFeatureMatrix,
    family: ProductionFamily,
) -> int:
    recipe = recipe_for(family)
    cutoff = datetime(2022, 12, 31, 18, tzinfo=SHANGHAI)
    count = 0
    for horizon in recipe.horizons:
        count += len(
            final_training_sample_ids(
                point_in_time_samples(matrix, horizon=horizon),
                recipe=recipe,
                purpose="development",
                training_at=cutoff,
            )
        )
    return count


def _candidate_sample_count(
    matrix: ProductionFeatureMatrix,
    family: ProductionFamily,
) -> int:
    recipe = recipe_for(family)
    start = datetime(2012, 12, 31, 18, tzinfo=SHANGHAI)
    cutoff = datetime(2022, 12, 31, 18, tzinfo=SHANGHAI)
    return sum(
        start <= row.feature_at <= cutoff and row.horizon_sessions in recipe.horizons
        for row in matrix.rows
    )


def _file_set(root: Path) -> tuple[str, ...]:
    return tuple(sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()))


def _required(value: str | None) -> str:
    assert value is not None
    return value
