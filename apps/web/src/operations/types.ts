export type PaperOperations = {
  as_of: string;
  execution_mode: "paper";
  account_mode: "simulation";
  broker_connection: "disconnected" | "readonly" | "connected";
  canary_state:
    | "not_authorized"
    | "awaiting_final_limit_approval"
    | "ready_to_submit"
    | "working"
    | "terminal"
    | "blocked";
  standing_mandate_id: string | null;
  authorization_id: string | null;
  instrument_id: string | null;
  side: "buy" | null;
  quantity: number | null;
  max_notional_cny: number | null;
  mandate_effective_from: string | null;
  mandate_effective_to: string | null;
  submission_window_start: string | null;
  submission_window_end: string | null;
  inherited_overlap: "allowed" | null;
  account_baseline_state: "missing" | "readonly_ready" | "blocked";
  inherited_position_count: number;
  open_order_count: number;
  intent_count: number;
  observation_count: number;
  blocker_codes: string[];
  next_action: string;
  broker_actions_allowed: boolean;
};

export type OperationsState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; value: OperationsPayload };

export type DailyPipelineStatus = {
  target_date: string;
  state:
    | "waiting_window"
    | "waiting_provider"
    | "running"
    | "current"
    | "stale"
    | "blocked"
    | "recovery_required"
    | "no_session";
  observed_l1_count: number;
  observed_l2_count: number;
  blocker_codes: string[];
  recovery_action: string | null;
  broker_actions_allowed: false;
};

export type DailyDecisionStatus = {
  signal_date: string;
  state: "waiting_data" | "running" | "current" | "blocked" | "recovery_required";
  shadow_preflight_state: "not_run" | "ready" | "blocked" | "no_action";
  paper_preflight_state: "not_run" | "ready" | "blocked";
  blocker_codes: string[];
  recovery_action: string | null;
  paper_dispatch_state: "disabled";
  broker_actions_allowed: false;
};

export type DailyRunState =
  | "waiting_window"
  | "waiting_provider"
  | "running"
  | "current"
  | "stale"
  | "blocked"
  | "recovery_required"
  | "lease_held";

export type DailyRunStatus = {
  run_id: string;
  target_date: string;
  base_snapshot_id: string;
  state: DailyRunState;
  current_step: "data_pipeline" | "decision_chain" | "backup_readiness" | null;
  data_commit_id: string | null;
  data_snapshot_id: string | null;
  rotation_snapshot_id: string | null;
  feature_snapshot_id: string | null;
  prediction_batch_id: string | null;
  portfolio_target_id: string | null;
  order_plan_id: string | null;
  backup_id: string | null;
  blocker_codes: string[];
  recovery_action: string | null;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  broker_actions_allowed: false;
};

export type DailyRunRequestAction = "run" | "recover" | "retry_provider";

export type DailyRunRequest = {
  request_id: string;
  request_key: string;
  action: DailyRunRequestAction;
  target_date: string | null;
  run_id: string | null;
  state: "pending" | "claimed" | "completed" | "superseded";
  created_at: string;
  updated_at: string;
  broker_actions_allowed: false;
};

export type DailyAttentionItem = {
  code: string;
  severity: "notice" | "warning" | "blocked";
  title: string;
  detail: string;
  action: DailyRunRequestAction | "view" | "install_scheduler";
};

export type DailyOperations = {
  as_of: string;
  pipeline: DailyPipelineStatus | null;
  decision: DailyDecisionStatus | null;
  latest_run: DailyRunStatus | null;
  recent_runs: DailyRunStatus[];
  schedule: {
    state: "not_installed" | "installed" | "paused" | "error";
    task_name: string;
    trigger_labels: string[];
    next_run_at: string | null;
    last_result: string | null;
    updated_at: string;
    broker_actions_allowed: false;
  };
  pending_request: DailyRunRequest | null;
  attention: DailyAttentionItem[];
  broker_actions_allowed: false;
};

export type OperationsPayload = {
  paper: PaperOperations;
  daily: DailyOperations | null;
};
