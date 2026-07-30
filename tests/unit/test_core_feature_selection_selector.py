from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.contracts import CoreUniverseDecision
from astramind_mini.strategy_research.core.feature_processing import (
    CoreCrossSectionEvidence,
    CoreCrossSectionStatus,
    CoreNeutralizationStatus,
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelEntry,
    CoreProcessedFeaturePanelManifest,
    CoreProcessedFeatureRow,
)
from astramind_mini.strategy_research.core.feature_selection import (
    STAGE_P_PRIORS_CONTENT_HASH,
    STAGE_P_TOKENIZER_RULES_HASH,
    CoreFeatureSelectionManifest,
    CoreSelectionFold,
    CoreSelectionPriorEntry,
    CoreSelectionPriorManifest,
    CoreSelectionReason,
    freeze_core_selection_fold,
    select_core_features,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreImputationSource,
    FeatureAvailabilityState,
)
from astramind_mini.strategy_research.core.labels import (
    CoreForwardReturnLabelBatch,
    CoreForwardReturnLabelRow,
    CoreForwardReturnLabelSpec,
    CoreLabelHorizon,
)

PACKAGE = "fixture-selection-package"
FEATURE_ID = "F"
FEATURE_KEY = "F@1.0.0"
REGISTRY_HASH = "sha256:" + "a" * 64
COMPUTATION_HASH = "sha256:" + "b" * 64
INSTRUMENTS = ("A", "B", "C", "D", "E")
START = date(2025, 1, 2)
CUTOFF = datetime(2026, 1, 1, tzinfo=UTC)


def _hash(value: object) -> str:
    return research_hash({"fixture": value})


def _decision(instrument: str, day: date) -> CoreUniverseDecision:
    return CoreUniverseDecision.model_construct(
        instrument_id=instrument,
        decision_date=day,
        research_member=True,
    )


def _daily_bundle(
    index: int,
    horizon: CoreLabelHorizon,
) -> tuple[
    CoreProcessedFeatureEnvelope,
    CoreProcessedFeaturePanelEntry,
    CoreForwardReturnLabelBatch,
]:
    day = START + timedelta(days=index)
    universe_hash = _hash(("u0", index))
    rows = tuple(
        CoreProcessedFeatureRow(
            instrument_id=instrument,
            feature_id=FEATURE_ID,
            feature_definition_version="1.0.0",
            availability_state=FeatureAvailabilityState.OBSERVED,
            value_raw=float(position),
            value_winsorized=float(position),
            value_standardized_observed=float(position),
            model_value=float(position),
            imputation_source=CoreImputationSource.NONE,
            is_missing=False,
            is_not_applicable=False,
        )
        for position, instrument in enumerate(INSTRUMENTS)
    )
    envelope = CoreProcessedFeatureEnvelope.model_construct(
        envelope_id=f"processed-{index}",
        content_hash=_hash(("processed", index)),
        decision_date=day,
        package_id=PACKAGE,
        definition_registry_hash=REGISTRY_HASH,
        computation_manifest_hash=COMPUTATION_HASH,
        universe_content_hash=universe_hash,
        feature_order=(FEATURE_ID,),
        instrument_order=INSTRUMENTS,
        rows=rows,
        cross_sections=(
            CoreCrossSectionEvidence(
                feature_id=FEATURE_ID,
                feature_definition_version="1.0.0",
                observed_count=5,
                missing_count=0,
                not_applicable_count=0,
                applicable_count=5,
                coverage=1.0,
                median_raw=2.0,
                mad_scale=1.0,
                winsor_lower=-3.0,
                winsor_upper=7.0,
                status=CoreCrossSectionStatus.READY,
                neutralization_status=CoreNeutralizationStatus.INSUFFICIENT_SAMPLE,
                neutralization_sample_count=5,
                neutralization_parameter_count=2,
            ),
        ),
        blocked_feature_ids=(),
    )
    panel_entry = CoreProcessedFeaturePanelEntry(
        decision_date=day,
        core_input_snapshot_id=f"input-{index}",
        core_input_content_hash=_hash(("input", index)),
        raw_envelope_id=f"raw-{index}",
        raw_envelope_content_hash=_hash(("raw", index)),
        processed_envelope_id=envelope.envelope_id,
        processed_envelope_content_hash=envelope.content_hash,
        universe_content_hash=universe_hash,
        control_panel_id=f"control-{index}",
        control_panel_content_hash=_hash(("control", index)),
    )
    label = _label_batch(
        day=day,
        index=index,
        horizon=horizon,
        universe_hash=universe_hash,
    )
    return envelope, panel_entry, label


def _label_batch(
    *,
    day: date,
    index: int,
    horizon: CoreLabelHorizon,
    universe_hash: str,
) -> CoreForwardReturnLabelBatch:
    rows = tuple(
        CoreForwardReturnLabelRow(
            instrument_id=instrument,
            research_member=True,
            absolute_return=float(position) / 10.0,
            percentile=float(position) / 4.0,
        )
        for position, instrument in enumerate(INSTRUMENTS)
    )
    return CoreForwardReturnLabelBatch.model_construct(
        batch_id=f"label-{horizon}-{index}",
        content_hash=_hash(("label", horizon, index)),
        spec=CoreForwardReturnLabelSpec(horizon=horizon),
        decision_date=day,
        decision_universe_content_hash=universe_hash,
        universe_rows=tuple(_decision(instrument, day) for instrument in INSTRUMENTS),
        label_data_snapshot_as_of=CUTOFF,
        label_available_cutoff=CUTOFF,
        matured=True,
        rows=rows,
    )


def _inputs(
    horizon: CoreLabelHorizon,
) -> tuple[
    CoreProcessedFeaturePanelManifest,
    tuple[CoreProcessedFeatureEnvelope, ...],
    tuple[CoreForwardReturnLabelBatch, ...],
]:
    bundles = tuple(_daily_bundle(index, horizon) for index in range(180))
    envelopes = tuple(item[0] for item in bundles)
    entries = tuple(item[1] for item in bundles)
    labels = tuple(item[2] for item in bundles)
    panel = CoreProcessedFeaturePanelManifest.model_construct(
        panel_manifest_id="panel",
        content_hash=_hash("panel"),
        package_id=PACKAGE,
        feature_order=(FEATURE_ID,),
        entries=entries,
    )
    return panel, envelopes, labels


def _prior() -> CoreSelectionPriorManifest:
    entry = CoreSelectionPriorEntry.model_construct(
        package_id=PACKAGE,
        feature_key=FEATURE_KEY,
        canonical_order=1,
        package_canonical_order=1,
        expected_direction=1,
        complexity=1,
    )
    return CoreSelectionPriorManifest.model_construct(
        entries=(entry,),
        package_bindings={
            PACKAGE: {
                "required_definition_registry_hash": REGISTRY_HASH,
                "computation_manifest_hash": COMPUTATION_HASH,
            }
        },
        tokenizer={"rules_hash": STAGE_P_TOKENIZER_RULES_HASH},
        priors_content_hash=STAGE_P_PRIORS_CONTENT_HASH,
    )


def _fold() -> CoreSelectionFold:
    dates = tuple(START + timedelta(days=index) for index in range(180))
    return freeze_core_selection_fold(
        decision_dates=dates,
        label_maturity_cutoff=CUTOFF,
        subfold_dates=(dates[:60], dates[60:120], dates[120:]),
    )


def test_selector_freezes_h20_and_h60_independently_from_exact_fold_parents() -> None:
    fold = _fold()
    manifests = []
    for horizon in (CoreLabelHorizon.H20, CoreLabelHorizon.H60):
        panel, envelopes, labels = _inputs(horizon)
        manifest = select_core_features(
            panel_manifest=panel,
            processed_envelopes=envelopes,
            label_batches=labels,
            fold=fold,
            horizon=horizon,
            prior_manifest=_prior(),
        )
        assert manifest.selected_feature_keys == (FEATURE_KEY,)
        assert manifest.feature_evidence[0].reason_code == CoreSelectionReason.SELECTED
        assert manifest.feature_evidence[0].bootstrap_p_value == pytest.approx(1 / 10001)
        assert len(manifest.processed_days) == len(manifest.label_batches) == 180
        manifests.append(manifest)
    assert manifests[0].manifest_id != manifests[1].manifest_id
    attack = manifests[0].model_dump()
    evidence = list(attack["feature_evidence"])
    evidence[0] = {**evidence[0], "bh_passed": False}
    attack["feature_evidence"] = tuple(evidence)
    body = {
        key: value for key, value in attack.items() if key not in {"manifest_id", "content_hash"}
    }
    attack_hash = research_hash({"schema": "core-feature-selection-manifest-v1", **body})
    attack["manifest_id"] = f"core-selection:{attack_hash.removeprefix('sha256:')}"
    attack["content_hash"] = attack_hash
    with pytest.raises(ValueError, match="BH evidence"):
        CoreFeatureSelectionManifest.model_validate(attack)


def test_selector_rejects_diagnostics_old_prior_and_future_tail() -> None:
    panel, envelopes, labels = _inputs(CoreLabelHorizon.H20)
    fold = _fold()
    with pytest.raises(ValueError, match="D1/D3/D5"):
        select_core_features(
            panel_manifest=panel,
            processed_envelopes=envelopes,
            label_batches=labels,
            fold=fold,
            horizon=CoreLabelHorizon.D1,
            prior_manifest=_prior(),
        )
    old_prior = _prior().model_copy(update={"priors_content_hash": "sha256:" + "0" * 64})
    with pytest.raises(ValueError, match="immutable Stage P prior"):
        select_core_features(
            panel_manifest=panel,
            processed_envelopes=envelopes,
            label_batches=labels,
            fold=fold,
            horizon=CoreLabelHorizon.H20,
            prior_manifest=old_prior,
        )
    extra_envelope, _, extra_label = _daily_bundle(180, CoreLabelHorizon.H20)
    with pytest.raises(ValueError, match="exactly match"):
        select_core_features(
            panel_manifest=panel,
            processed_envelopes=(*envelopes, extra_envelope),
            label_batches=(*labels, extra_label),
            fold=fold,
            horizon=CoreLabelHorizon.H20,
            prior_manifest=_prior(),
        )
