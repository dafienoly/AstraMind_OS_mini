.PHONY: bootstrap doctor dev check docs-check e2e-smoke provider-probe miniqmt-l1-capture miniqmt-account-reconcile continuous-shadow-initialize continuous-shadow-start tactical-research-smoke tactical-event-backfill tactical-sealed-replay shadow-smoke data-snapshot data-backfill data-backfill-h2 data-backfill-h3 data-backfill-h4 industry-data-foundation market-rotation contracts-generate contracts-check

bootstrap:
	uv sync --locked
	pnpm install --frozen-lockfile
	pnpm exec playwright install chromium

doctor:
	uv run python scripts/doctor.py

dev:
	uv run python scripts/dev.py

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run pytest
	pnpm run lint
	pnpm run typecheck
	pnpm run test
	pnpm run build
	uv run python scripts/check_architecture.py
	uv run python scripts/check_repository.py
	uv run python scripts/generate_contract_schemas.py --check

docs-check:
	uv run python scripts/check_repository.py

e2e-smoke:
	uv run python scripts/e2e_smoke.py

provider-probe:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env" && exit 2)
	uv run python scripts/provider_probe.py --provider-env-file "$(PROVIDER_ENV_FILE)"

miniqmt-l1-capture:
	uv run python scripts/capture_miniqmt_l1.py --seconds "$(or $(CAPTURE_SECONDS),5)"

miniqmt-account-reconcile:
	uv run python scripts/reconcile_miniqmt_account.py

continuous-shadow-initialize:
	@test -n "$(ACCOUNT_SNAPSHOT_ID)" || (echo "请设置 ACCOUNT_SNAPSHOT_ID" && exit 2)
	@test -n "$(RECONCILIATION_REPORT_ID)" || (echo "请设置 RECONCILIATION_REPORT_ID" && exit 2)
	uv run python scripts/initialize_continuous_shadow.py \
		--account-snapshot-id "$(ACCOUNT_SNAPSHOT_ID)" \
		--reconciliation-report-id "$(RECONCILIATION_REPORT_ID)"

continuous-shadow-start:
	@test -n "$(SNAPSHOT_ID)" || (echo "请设置 SNAPSHOT_ID" && exit 2)
	@test -n "$(SIGNAL_DATE)" || (echo "请设置 SIGNAL_DATE=YYYY-MM-DD" && exit 2)
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE" && exit 2)
	uv run python scripts/start_promoted_shadow_cycle.py \
		--snapshot-id "$(SNAPSHOT_ID)" \
		--signal-date "$(SIGNAL_DATE)" \
		--provider-env-file "$(PROVIDER_ENV_FILE)"

tactical-research-smoke:
	@test -n "$(SNAPSHOT_ID)" || (echo "请设置 SNAPSHOT_ID" && exit 2)
	@test -n "$(AS_OF)" || (echo "请设置 AS_OF=YYYY-MM-DD" && exit 2)
	uv run python scripts/run_tactical_research.py \
		--snapshot-id "$(SNAPSHOT_ID)" --as-of "$(AS_OF)"

tactical-event-backfill:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env" && exit 2)
	@test -n "$(BASE_SNAPSHOT_ID)" || (echo "请设置 BASE_SNAPSHOT_ID" && exit 2)
	uv run python scripts/backfill_tactical_events.py \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		--base-snapshot-id "$(BASE_SNAPSHOT_ID)"

industry-data-foundation:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env" && exit 2)
	@test -n "$(BASE_SNAPSHOT_ID)" || (echo "请设置 BASE_SNAPSHOT_ID" && exit 2)
	@test -n "$(END_DATE)" || (echo "请设置 END_DATE=YYYY-MM-DD" && exit 2)
	uv run python scripts/publish_industry_foundation.py \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		--base-snapshot-id "$(BASE_SNAPSHOT_ID)" \
		--end-date "$(END_DATE)"

market-rotation:
	@test -n "$(SNAPSHOT_ID)" || (echo "请设置 SNAPSHOT_ID=包含行业基础的准确快照" && exit 2)
	uv run python scripts/publish_market_rotation.py --data-snapshot-id "$(SNAPSHOT_ID)"

tactical-sealed-replay:
	@test -n "$(SNAPSHOT_ID)" || (echo "请设置包含事件数据的 SNAPSHOT_ID" && exit 2)
	uv run python scripts/run_tactical_sealed_replay.py --snapshot-id "$(SNAPSHOT_ID)"

shadow-smoke:
	uv run python scripts/run_shadow_smoke.py

data-snapshot:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env" && exit 2)
	uv run python scripts/publish_data_snapshot.py --provider-env-file "$(PROVIDER_ENV_FILE)"

data-backfill:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env" && exit 2)
	@test -n "$(LEGACY_DATA_ROOT)" || (echo "请设置 LEGACY_DATA_ROOT=/home/ly/AstraMindResearchData" && exit 2)
	@test -n "$(LEGACY_DATASET_VERSION)" || (echo "请设置 LEGACY_DATASET_VERSION" && exit 2)
	@test -n "$(BASE_SNAPSHOT_ID)" || (echo "请设置 BASE_SNAPSHOT_ID" && exit 2)
	uv run python scripts/import_legacy_market_history.py \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		--legacy-data-root "$(LEGACY_DATA_ROOT)" \
		--legacy-dataset-version "$(LEGACY_DATASET_VERSION)" \
		--base-snapshot-id "$(BASE_SNAPSHOT_ID)"

data-backfill-h2:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env" && exit 2)
	@test -n "$(LEGACY_DATA_ROOT)" || (echo "请设置 LEGACY_DATA_ROOT=/home/ly/AstraMindResearchData" && exit 2)
	@test -n "$(LEGACY_DATASET_VERSION)" || (echo "请设置 LEGACY_DATASET_VERSION" && exit 2)
	@test -n "$(BASE_SNAPSHOT_ID)" || (echo "请设置 BASE_SNAPSHOT_ID" && exit 2)
	uv run python scripts/import_legacy_constraints.py \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		--legacy-data-root "$(LEGACY_DATA_ROOT)" \
		--legacy-dataset-version "$(LEGACY_DATASET_VERSION)" \
		--base-snapshot-id "$(BASE_SNAPSHOT_ID)"

data-backfill-h3:
	@test -n "$(LEGACY_DATA_ROOT)" || (echo "请设置 LEGACY_DATA_ROOT=/home/ly/AstraMindResearchData" && exit 2)
	@test -n "$(LEGACY_DATASET_VERSION)" || (echo "请设置 LEGACY_DATASET_VERSION" && exit 2)
	@test -n "$(BASE_SNAPSHOT_ID)" || (echo "请设置 BASE_SNAPSHOT_ID" && exit 2)
	uv run python scripts/project_historical_status.py \
		--legacy-data-root "$(LEGACY_DATA_ROOT)" \
		--legacy-dataset-version "$(LEGACY_DATASET_VERSION)" \
		--base-snapshot-id "$(BASE_SNAPSHOT_ID)"

data-backfill-h4:
	@test -n "$(LEGACY_DATA_ROOT)" || (echo "请设置 LEGACY_DATA_ROOT=/home/ly/AstraMindResearchData" && exit 2)
	@test -n "$(LEGACY_DATASET_VERSION)" || (echo "请设置 LEGACY_DATASET_VERSION" && exit 2)
	@test -n "$(BASE_SNAPSHOT_ID)" || (echo "请设置 BASE_SNAPSHOT_ID" && exit 2)
	uv run python scripts/project_corporate_actions.py \
		--legacy-data-root "$(LEGACY_DATA_ROOT)" \
		--legacy-dataset-version "$(LEGACY_DATASET_VERSION)" \
		--base-snapshot-id "$(BASE_SNAPSHOT_ID)"

contracts-generate:
	uv run python scripts/generate_contract_schemas.py

contracts-check:
	uv run python scripts/generate_contract_schemas.py --check
