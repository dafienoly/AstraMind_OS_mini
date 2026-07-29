.PHONY: bootstrap doctor dev check docs-check e2e-smoke provider-probe historical-price-limit-probe miniqmt-l1-capture miniqmt-account-reconcile miniqmt-paper-readonly-handshake paper-canary-authorize paper-canary-run paper-canary-settle paper-canary-stage-limit paper-canary-approve paper-canary-submit paper-canary-status paper-canary-recover paper-canary-cancel paper-canary-converge paper-offline-guard paper-offline-fault-drill continuous-shadow-initialize continuous-shadow-start continuous-shadow-advance ops-plan ops-backup ops-recovery-drill tactical-research-smoke tactical-event-backfill tactical-sealed-replay shadow-smoke data-snapshot data-backfill data-backfill-h2 data-backfill-h3 data-backfill-h4 industry-data-foundation market-rotation daily-data-update daily-data-status daily-decision-run daily-decision-status daily-run daily-run-status daily-run-recover daily-schedule-trigger daily-schedule-preview daily-schedule-status daily-schedule-install daily-schedule-pause daily-schedule-uninstall contracts-generate contracts-check

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

miniqmt-paper-readonly-handshake:
	uv run python scripts/handshake_miniqmt_paper_readonly.py

paper-canary-authorize:
	@test -n "$(CYCLE_ARTIFACT)" || (echo "请设置 CYCLE_ARTIFACT=var/.../cycle.json" && exit 2)
	@test -n "$(APPROVED_AT)" || (echo "请设置 APPROVED_AT=带时区ISO时间" && exit 2)
	uv run python scripts/prepare_paper_canary.py \
		--cycle-artifact "$(CYCLE_ARTIFACT)" \
		--instrument "605208.SH" \
		--quantity 100 \
		--max-notional 50000 \
		--mandate-start "2026-07-29T09:30:00+08:00" \
		--mandate-end "2026-07-29T10:00:00+08:00" \
		--submission-start "2026-07-29T09:35:00+08:00" \
		--submission-end "2026-07-29T09:45:00+08:00" \
		--approved-at "$(APPROVED_AT)"

paper-canary-run:
	uv run python scripts/run_paper_canary.py

paper-canary-settle:
	uv run python scripts/settle_paper_canary.py

paper-canary-stage-limit:
	uv run python scripts/handshake_miniqmt_paper_readonly.py
	uv run python scripts/stage_paper_canary_limit.py

paper-canary-approve:
	@test -n "$(PROPOSAL_ID)" || (echo "请设置 PROPOSAL_ID" && exit 2)
	@test -n "$(EXACT_LIMIT_PRICE)" || (echo "请设置 EXACT_LIMIT_PRICE" && exit 2)
	@test -n "$(APPROVED_AT)" || (echo "请设置 APPROVED_AT=带时区ISO时间" && exit 2)
	@test -n "$(EFFECTIVE_TO)" || (echo "请设置 EFFECTIVE_TO=不超过3分钟且不晚于09:45" && exit 2)
	uv run python scripts/approve_paper_canary_limit.py \
		--proposal-id "$(PROPOSAL_ID)" \
		--confirm-limit-price "$(EXACT_LIMIT_PRICE)" \
		--approved-at "$(APPROVED_AT)" \
		--effective-to "$(EFFECTIVE_TO)" \
		--confirm "APPROVE_EXACT_PAPER_CANARY"

paper-canary-submit:
	@test -n "$(APPROVAL_ID)" || (echo "请设置 APPROVAL_ID" && exit 2)
	uv run python scripts/submit_paper_canary.py \
		--approval-id "$(APPROVAL_ID)" \
		--confirm "SUBMIT_ONE_APPROVED_PAPER_CANARY"

paper-canary-status:
	@test -n "$(APPROVAL_ID)" || (echo "请设置 APPROVAL_ID" && exit 2)
	uv run python scripts/control_paper_canary.py \
		--action status --approval-id "$(APPROVAL_ID)" \
		$(if $(INTENT_ID),--intent-id "$(INTENT_ID)",)

paper-canary-recover:
	@test -n "$(APPROVAL_ID)" || (echo "请设置 APPROVAL_ID" && exit 2)
	uv run python scripts/control_paper_canary.py \
		--action recover --approval-id "$(APPROVAL_ID)" \
		$(if $(INTENT_ID),--intent-id "$(INTENT_ID)",)

paper-canary-cancel:
	@test -n "$(APPROVAL_ID)" || (echo "请设置 APPROVAL_ID" && exit 2)
	uv run python scripts/control_paper_canary.py \
		--action cancel --approval-id "$(APPROVAL_ID)" \
		--confirm "CANCEL_THIS_PAPER_CANARY_ONLY" \
		$(if $(INTENT_ID),--intent-id "$(INTENT_ID)",)

paper-canary-converge:
	@test -n "$(APPROVAL_ID)" || (echo "请设置 APPROVAL_ID" && exit 2)
	uv run python scripts/converge_paper_canary.py \
		--approval-id "$(APPROVAL_ID)" \
		$(if $(INTENT_ID),--intent-id "$(INTENT_ID)",)

paper-offline-guard:
	uv run python scripts/run_offline_paper_guard.py \
		$(if $(LOGICAL_DATE),--logical-date "$(LOGICAL_DATE)",) \
		$(if $(CYCLE_ARTIFACT),--cycle-artifact "$(CYCLE_ARTIFACT)",)

paper-offline-fault-drill:
	uv run python scripts/drill_offline_paper_faults.py \
		$(if $(LOGICAL_DATE),--logical-date "$(LOGICAL_DATE)",)

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

continuous-shadow-advance:
	@test -n "$(CYCLE_ARTIFACT)" || (echo "请设置 CYCLE_ARTIFACT=var/.../cycle.json" && exit 2)
	@test -n "$(SNAPSHOT_ID)" || (echo "请设置 SNAPSHOT_ID=包含观察日的准确快照" && exit 2)
	@test -n "$(THROUGH_DATE)" || (echo "请设置 THROUGH_DATE=YYYY-MM-DD" && exit 2)
	uv run python scripts/advance_continuous_shadow_cycle.py \
		--cycle-artifact "$(CYCLE_ARTIFACT)" \
		--snapshot-id "$(SNAPSHOT_ID)" \
		--through-date "$(THROUGH_DATE)"

ops-plan:
	@test -n "$(TRADING_DATE)" || (echo "请设置 TRADING_DATE=YYYY-MM-DD" && exit 2)
	@test -n "$(NEXT_TRADING_DATE)" || (echo "请设置 NEXT_TRADING_DATE=YYYY-MM-DD" && exit 2)
	@test -n "$(OPS_AT)" || (echo "请设置 OPS_AT=带时区 ISO 时间" && exit 2)
	uv run python scripts/plan_local_operations.py \
		--trading-date "$(TRADING_DATE)" \
		--next-trading-date "$(NEXT_TRADING_DATE)" \
		--at "$(OPS_AT)" \
		$(if $(filter true,$(PROVIDER_COMPLETE)),--provider-complete,) \
		$(if $(filter true,$(PIPELINE_COMPLETED)),--pipeline-completed,) \
		$(if $(filter true,$(BACKUP_READY)),--backup-ready,)

ops-backup:
	uv run python scripts/backup_local_state.py \
		--reason "$(or $(BACKUP_REASON),manual)" \
		$(if $(LOGICAL_DATE),--logical-date "$(LOGICAL_DATE)",)

ops-recovery-drill:
	@test -n "$(BACKUP_ID)" || (echo "请设置 BACKUP_ID=local-backup:..." && exit 2)
	uv run python scripts/drill_local_recovery.py --backup-id "$(BACKUP_ID)"

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
		--base-snapshot-id "$(BASE_SNAPSHOT_ID)" \
		$(if $(START_DATE),--start-date "$(START_DATE)",) \
		$(if $(END_DATE),--end-date "$(END_DATE)",) \
		$(if $(filter true,$(REPUBLISH)),--republish,)

historical-price-limit-probe:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env" && exit 2)
	uv run python scripts/probe_historical_price_limits.py \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		$(if $(BASE_SNAPSHOT_ID),--base-snapshot-id "$(BASE_SNAPSHOT_ID)",) \
		$(if $(START_DATE),--start-date "$(START_DATE)",) \
		$(if $(END_DATE),--end-date "$(END_DATE)",)

industry-data-foundation:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env" && exit 2)
	@test -n "$(BASE_SNAPSHOT_ID)" || (echo "请设置 BASE_SNAPSHOT_ID" && exit 2)
	@test -n "$(END_DATE)" || (echo "请设置 END_DATE=YYYY-MM-DD" && exit 2)
	uv run python scripts/publish_industry_foundation.py \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		--base-snapshot-id "$(BASE_SNAPSHOT_ID)" \
		--end-date "$(END_DATE)" \
		$(if $(filter true,$(INCLUDE_L2)),--include-l2,)

market-rotation:
	@test -n "$(SNAPSHOT_ID)" || (echo "请设置 SNAPSHOT_ID=包含行业基础的准确快照" && exit 2)
	uv run python scripts/publish_market_rotation.py --data-snapshot-id "$(SNAPSHOT_ID)"

daily-data-update:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env" && exit 2)
	@test -n "$(TARGET_DATE)" || (echo "请设置 TARGET_DATE=最近完成交易日 YYYY-MM-DD" && exit 2)
	uv run python scripts/run_daily_data_pipeline.py \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		--target-date "$(TARGET_DATE)" \
		$(if $(BASE_SNAPSHOT_ID),--base-snapshot-id "$(BASE_SNAPSHOT_ID)",)

daily-data-status:
	uv run python scripts/run_daily_data_pipeline.py --status

daily-decision-run:
	uv run python scripts/run_daily_decision_chain.py

daily-decision-status:
	uv run python scripts/run_daily_decision_chain.py --status

daily-run:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/path/to/provider.env" && exit 2)
	@test -n "$(TARGET_DATE)" || (echo "请设置 TARGET_DATE=最近完成交易日 YYYY-MM-DD" && exit 2)
	uv run python scripts/run_daily.py \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		--target-date "$(TARGET_DATE)" \
		$(if $(BASE_SNAPSHOT_ID),--base-snapshot-id "$(BASE_SNAPSHOT_ID)",)

daily-run-status:
	uv run python scripts/run_daily.py --status $(if $(RUN_ID),--run-id "$(RUN_ID)",)

daily-run-recover:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/path/to/provider.env" && exit 2)
	@test -n "$(RUN_ID)" || (echo "请设置 RUN_ID=daily-run:..." && exit 2)
	uv run python scripts/run_daily.py \
		--recover --run-id "$(RUN_ID)" \
		--provider-env-file "$(PROVIDER_ENV_FILE)"

daily-schedule-trigger:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/path/to/provider.env" && exit 2)
	uv run python scripts/run_daily_scheduler.py \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		$(if $(SCHEDULE_AT),--at "$(SCHEDULE_AT)",) \
		$(if $(filter true,$(DRY_RUN)),--dry-run,)

daily-schedule-preview:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/path/to/provider.env" && exit 2)
	uv run python scripts/manage_daily_schedule.py preview \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		$(if $(DISTRO),--distro "$(DISTRO)",)

daily-schedule-status:
	uv run python scripts/manage_daily_schedule.py status

daily-schedule-install:
	@test -n "$(PROVIDER_ENV_FILE)" || (echo "请设置 PROVIDER_ENV_FILE=/path/to/provider.env" && exit 2)
	@test -n "$(CONFIRM_TASK_NAME)" || (echo "请精确确认 CONFIRM_TASK_NAME" && exit 2)
	@test -n "$(CONFIRM_WORKDIR)" || (echo "请精确确认 CONFIRM_WORKDIR" && exit 2)
	uv run python scripts/manage_daily_schedule.py install \
		--provider-env-file "$(PROVIDER_ENV_FILE)" \
		--confirm-task-name "$(CONFIRM_TASK_NAME)" \
		--confirm-workdir "$(CONFIRM_WORKDIR)" \
		$(if $(DISTRO),--distro "$(DISTRO)",)

daily-schedule-pause:
	uv run python scripts/manage_daily_schedule.py pause

daily-schedule-uninstall:
	uv run python scripts/manage_daily_schedule.py uninstall

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
