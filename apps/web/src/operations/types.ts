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
  | { kind: "ready"; value: PaperOperations };
