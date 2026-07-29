export type PriceCandle = {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume_lots: number;
  amount_cny: number | null;
};

export type BroadIndex = {
  instrument_id: string;
  instrument_name: string;
  latest_trade_date: string;
  latest_close: number;
  change: number;
  percent_change: number;
  return_20d: number | null;
  drawdown_250d: number | null;
  candles: PriceCandle[];
};

export type IndustryHeatRow = {
  industry_code: string;
  industry_name: string;
  trade_date: string;
  percent_change: number;
  relative_strength: number;
  breadth_ratio: number | null;
  advancing: number;
  declining: number;
  member_count: number;
  covered_member_count: number;
  coverage_ratio: number;
  amount_change_20d: number | null;
  volatility_20d: number | null;
  price_earnings: number | null;
  price_book: number | null;
  leading_instrument_id: string | null;
  leading_instrument_name: string | null;
  leading_percent_change: number | null;
  known_gaps: string[];
};

export type MarketDashboardProjection = {
  status: "ready" | "stale" | "blocked";
  data_snapshot_id: string;
  as_of: string;
  evidence_cutoff: string | null;
  projection_version: string;
  selected_index_id: string | null;
  indexes: BroadIndex[];
  breadth: {
    advancing: number;
    declining: number;
    unchanged: number;
    advance_ratio: number;
    new_high_250d: number;
    new_low_250d: number;
    upper_limit_locked: number;
    lower_limit_locked: number;
  } | null;
  liquidity: {
    amount_cny: number;
    amount_change_20d: number | null;
    amount_percentile_250d: number | null;
  } | null;
  regime: {
    state: "strong" | "balanced" | "weak" | "divergent" | "unknown";
    label: string;
    confidence: number;
    definition_version: string;
    observations: string[];
  } | null;
  industries: IndustryHeatRow[];
  known_gaps: string[];
};

export type RealtimeIndexQuote = {
  instrument_id: string;
  last_price: number;
  change_percent: number | null;
  market_time_ms: number | null;
};

export type RealtimeIndustryHeat = {
  industry_code: string;
  change_percent: number;
  observed_constituents: number;
};

export type RealtimeMarketProjection = {
  projection_id: string;
  provider: string;
  session_id: string;
  state: "current" | "stale" | "disconnected";
  as_of: string;
  latest_received_at: string | null;
  latest_market_time_ms: number | null;
  granularity_ms: number;
  quote_count: number;
  breadth_observed: number;
  breadth_expected: number | null;
  breadth_coverage_ratio: number | null;
  advancing: number;
  declining: number;
  unchanged: number;
  total_amount: number;
  indexes: RealtimeIndexQuote[];
  industries: RealtimeIndustryHeat[];
  known_gaps: string[];
};

export type RealtimeBookLevel = {
  level: number;
  price: number | null;
  volume: number | null;
};

export type RealtimeInstrumentQuote = {
  instrument_id: string;
  instrument_name: string | null;
  instrument_type: "stock" | "etf" | "index" | "other";
  industry_code: string | null;
  market_time_ms: number | null;
  received_at: string;
  last_price: number | null;
  previous_close: number | null;
  change_percent: number | null;
  open_price: number | null;
  high_price: number | null;
  low_price: number | null;
  volume: number | null;
  amount: number | null;
  upper_limit: number | null;
  lower_limit: number | null;
  stock_status: number | null;
  status_label: string;
  bids: RealtimeBookLevel[];
  asks: RealtimeBookLevel[];
};

export type RealtimeMinuteBar = {
  provider: string;
  session_id: string;
  instrument_id: string;
  minute: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
  observation_count: number;
};

export type RealtimeInstrumentProjection = {
  projection_id: string;
  provider: string;
  session_id: string;
  state: "current" | "stale" | "disconnected";
  as_of: string;
  market_date: string;
  quotes: RealtimeInstrumentQuote[];
  open_minutes: RealtimeMinuteBar[];
  known_gaps: string[];
};

export type RealtimeInstrumentDetail = {
  projection_id: string;
  provider: string;
  session_id: string;
  state: "current" | "stale" | "disconnected";
  as_of: string;
  quote: RealtimeInstrumentQuote;
  minutes: RealtimeMinuteBar[];
  known_gaps: string[];
};

export type RealtimeInstrumentSearchResult = Pick<RealtimeInstrumentQuote,
  "instrument_id" | "instrument_name" | "instrument_type" | "last_price"
  | "change_percent" | "status_label">;

export type LifecycleStage =
  | "明显退潮"
  | "退潮观察"
  | "强势扩散"
  | "低位修复"
  | "极端低位"
  | "方向未明";

export type IndustryLifecyclePoint = {
  industry_code: string;
  industry_name: string;
  stage: LifecycleStage;
  confidence: "high" | "medium" | "low";
  strong_participation: number | null;
  low_participation: number | null;
  strong_change_5d: number | null;
  low_change_5d: number | null;
  strong_peak_20d: number | null;
  strong_drawdown_20d: number | null;
  amount_share_20d: number | null;
  eligible_member_count: number;
  valid_member_count: number;
  coverage_ratio: number;
  recently_transitioned: boolean;
  trajectory: {
    trade_date: string;
    strong_participation: number;
    low_participation: number;
  }[];
  known_gaps: string[];
};

export type IndustryLifecycleProjection = {
  status: "ready" | "stale" | "blocked";
  data_snapshot_id: string;
  as_of: string;
  evidence_cutoff: string | null;
  taxonomy_version: string | null;
  method_version: string;
  industries: IndustryLifecyclePoint[];
  known_gaps: string[];
};

export type IndustryLifecycleIntradayProjection = {
  provider: string;
  session_id: string;
  state: "current" | "stale" | "disconnected" | "blocked";
  as_of: string;
  anchor_date: string;
  method_version: "lifecycle-intraday-overlay-v1.0.0";
  points: {
    industry_code: string;
    strong_participation: number;
    low_participation: number;
    valid_member_count: number;
    coverage_ratio: number;
  }[];
  known_gaps: string[];
};

export type IndustryResearchRow = {
  instrument_id: string;
  instrument_name: string;
  membership_effective_as_of: string;
  overall_priority: number | null;
  event_sentiment_score: number | null;
  technical_volume_score: number | null;
  fundamental_score: number | null;
  risk_score: number | null;
  reversal_repair_score: number | null;
  coverage: number;
  research_label: "优先研究" | "积极关注" | "中性观察" | "数据不足";
  evidence_cutoff: string;
  known_gaps: string[];
};

export type IndustryResearchRankingSnapshot = {
  status: "ready" | "stale" | "blocked";
  ranking_snapshot_id: string;
  data_snapshot_id: string;
  lifecycle_snapshot_id: string;
  as_of: string;
  evidence_cutoff: string;
  taxonomy: "SW";
  taxonomy_version: string;
  industry_code: string;
  industry_name: string;
  lifecycle_stage: string;
  scoring_definition_version: string;
  member_count: number;
  covered_member_count: number;
  content_hash: string;
  rows: IndustryResearchRow[];
  selected_instrument_id: string | null;
  candles: PriceCandle[];
  weekly_candles: PriceCandle[];
  monthly_candles: PriceCandle[];
  known_gaps: string[];
};

export type EtfRotationCandidate = {
  industry_code: string;
  industry_name: string;
  lifecycle_stage: string;
  lifecycle_confidence: string;
  etf_code: string | null;
  etf_name: string | null;
  mapping_tier: string;
  state: "eligible" | "context_only" | "rejected" | "stale" | "unavailable";
  overall_score: number | null;
  lifecycle_score: number | null;
  relative_strength_score: number | null;
  price_structure_score: number | null;
  liquidity_score: number | null;
  return_20d: number | null;
  return_60d: number | null;
  median_amount_20d_cny: number | null;
  latest_size_cny: number | null;
  spread_proxy_bps: number | null;
  spread_evidence_kind: "corwin_schultz_ohlc_proxy" | "unavailable";
  tracking_error_60d: number | null;
  tracking_evidence_kind: "sw_l1_exposure_proxy" | "unavailable";
  price_conclusion: string;
  rejection_reasons: string[];
  candles: PriceCandle[];
  weekly_candles: PriceCandle[];
  monthly_candles: PriceCandle[];
};

export type EtfRotationProjection = {
  status: "ready" | "stale" | "blocked";
  rotation_snapshot_id: string;
  data_snapshot_id: string;
  as_of: string;
  evidence_cutoff: string | null;
  strategy_version: string;
  mapping_version: string;
  spread_proxy_threshold_bps: number;
  tracking_proxy_threshold: number;
  funnel: {
    industry_count: number;
    exact_mapping_count: number;
    foundation_count: number;
    evidence_gate_count: number;
    eligible_count: number;
  };
  candidates: EtfRotationCandidate[];
  target_draft: {
    status: "draft" | "cash_only" | "blocked";
    weights: {
      industry_code: string;
      etf_code: string;
      target_weight: number;
      reason: string;
    }[];
    cash_weight: number;
    max_gross_weight: number;
    current_weights_observed: false;
    portfolio_target_created: false;
    order_plan_created: false;
    known_gaps: string[];
  };
  replay: {
    status: "blocked" | "candidate_frozen" | "diagnostic";
    evidence_label: string;
    start_date: string | null;
    end_date: string | null;
    decision_count: number;
    total_return: number | null;
    max_drawdown: number | null;
    turnover: number | null;
    estimated_cost_cny: number | null;
    next_open_execution: true;
    initial_research_cash_cny: number;
    commission_rate: number;
    minimum_commission_cny: number;
    slippage_bps_per_side: number;
    stamp_duty_rate: number;
    promotion_evidence_eligible: false;
    known_gaps: string[];
  };
  selected_etf_code: string | null;
  known_gaps: string[];
  broker_actions_allowed: false;
};
