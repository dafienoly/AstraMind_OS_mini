import type {
  PriceCandle,
  RealtimeInstrumentQuote,
  RealtimeMinuteBar,
} from "../market-dashboard/types";
import type { StockEvidence } from "../market/rotationTypes";

export type StockInspectionOrigin =
  | "watchlist"
  | "industry_rotation"
  | "industry_lifecycle"
  | "industry_ranking"
  | "strategy_candidate"
  | "portfolio_holding"
  | "attention_case";

export type StockInspectionMode =
  | "current"
  | "completed"
  | "historical_replay"
  | "sealed_evidence";

export type StockReturnTarget =
  | "market_stocks"
  | "industry_rotation"
  | "industry_lifecycle"
  | "industry_ranking"
  | "strategy_arena"
  | "portfolio"
  | "today";

export type StockInspectionFocus = {
  focus_id: string;
  instrument_id: string;
  origin: StockInspectionOrigin;
  as_of: string;
  data_snapshot_id: string;
  industry_code: string | null;
  cohort_id: string | null;
  strategy_version_id: string | null;
  portfolio_snapshot_id: string | null;
  attention_case_id: string | null;
  mode: StockInspectionMode;
  return_target: StockReturnTarget;
  created_at: string;
};

export type EvidenceSectionIdentity = {
  state: "ready" | "unavailable" | "blocked";
  as_of: string;
  provider: string;
  content_identity: string;
  known_gaps: string[];
};

export type StockWorkbenchProjection = {
  focus: StockInspectionFocus;
  instrument_identity: {
    instrument_id: string;
    instrument_name: string;
    exchange: string;
    market: string;
    risk_status: string | null;
    is_special_treatment: boolean | null;
  };
  completed_market_evidence: {
    evidence: EvidenceSectionIdentity;
    daily: PriceCandle[];
    weekly: PriceCandle[];
    monthly: PriceCandle[];
  };
  realtime_market_overlay: {
    state: "current" | "stale" | "disconnected";
    provider: string;
    session_id: string;
    as_of: string;
    quote: RealtimeInstrumentQuote;
    minutes: RealtimeMinuteBar[];
    known_gaps: string[];
  } | null;
  industry_context: {
    evidence: EvidenceSectionIdentity;
    taxonomy: "SW";
    taxonomy_version: string;
    l1_code: string | null;
    l1_name: string | null;
    l2_code: string | null;
    l2_name: string | null;
  };
  stock_evidence: StockEvidence;
  content_identity: string;
  known_gaps: string[];
};
