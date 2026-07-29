export type MarketModelFamily =
  | "industry_heat"
  | "industry_rotation"
  | "industry_lifecycle"
  | "industry_research_ranking"
  | "etf_rotation";

export type MarketModelState =
  | "active_v2"
  | "unvalidated_v2"
  | "fallback_v1"
  | "blocked";

export type MarketEvidenceState =
  | "development_only"
  | "unvalidated"
  | "supported"
  | "unsupported"
  | "blocked";

export interface MarketModelStatusItem {
  model_family: MarketModelFamily;
  display_name: string;
  state: MarketModelState;
  method_version: string;
  fallback_method_version: string;
  manifest_id: string | null;
  evidence_bundle_id: string | null;
  evidence_state: MarketEvidenceState;
  effective_at: string | null;
  reason_codes: string[];
  broker_actions_allowed: false;
}

export interface MarketModelStatusProjection {
  status_id: string;
  as_of: string;
  models: MarketModelStatusItem[];
  known_gaps: string[];
  broker_actions_allowed: false;
}
