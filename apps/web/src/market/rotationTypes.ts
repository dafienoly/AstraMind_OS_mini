export type Quadrant = "leading" | "weakening" | "lagging" | "improving";

export interface RotationPoint {
  industry_code: string;
  industry_name: string;
  trade_date: string;
  relative_trend: number;
  relative_momentum: number;
  quadrant: Quadrant;
  coverage: number;
  constituent_count: number;
  direction_x: number;
  direction_y: number;
  overflow: boolean;
  raw_z_trend?: number | null;
  raw_z_momentum?: number | null;
  display_transform_version?: string | null;
}

export interface VisualRotationPoint extends RotationPoint {
  display_trend: number;
  display_momentum: number;
}

export interface RotationTrail {
  industryCode: string;
  industryName: string;
  points: VisualRotationPoint[];
  selected: boolean;
  color: string;
  motionState: MotionState;
}

export type TrailMode = "selected" | "filtered" | "all";
export type RotationSpeed = 0.5 | 1 | 2;
export type PlaybackMode = "daily" | "continuous";
export type ContinuousDuration = 10 | 20 | 40;
export type MotionState =
  | "accelerating_up"
  | "decelerating_up"
  | "accelerating_down"
  | "decelerating_down"
  | "steady";

export interface RotationEvent {
  industry_code: string;
  industry_name: string;
  from_quadrant: Quadrant;
  to_quadrant: Quadrant;
  first_cross_date: string;
  confirmed_date: string;
  formula_version: string;
}

export interface RotationSnapshot {
  rotation_snapshot_id: string;
  data_snapshot_id: string;
  as_of: string;
  benchmark_id: string;
  benchmark_definition_version: string;
  formula: {
    formula_version: string;
    fast_window: number;
    slow_window: number;
    momentum_window: number;
    warmup_sessions: number;
    output_sessions: number;
    scale: number;
    clip_z: number;
    neutral_band: number;
    confirmation_sessions: number;
    required_industry_coverage: number;
    minimum_constituent_count: number;
    rounding_decimals: number;
  };
  taxonomy: "SW";
  taxonomy_version: string;
  industry_count: number;
  covered_industry_count: number;
  coverage_rule: string;
  date_range: [string, string];
  dates: string[];
  points: RotationPoint[];
  events: RotationEvent[];
  created_at: string;
  content_hash: string;
  known_gaps: string[];
}

export interface IndustryHierarchyNode {
  code: string;
  name: string;
  level: "L1" | "L2" | "stock";
  parent_code: string | null;
}

export interface IndustryHierarchyView {
  status: "ready" | "blocked";
  data_snapshot_id: string;
  as_of: string;
  level: "L1" | "L2" | "stock";
  comparison_scope: "l1" | "siblings" | "all_l2" | "members";
  benchmark_id: string;
  parent_code: string | null;
  selected_code: string | null;
  nodes: IndustryHierarchyNode[];
  rotation: RotationSnapshot | null;
  candles: {
    trade_date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume_lots: number;
    amount_cny: number | null;
  }[];
  weekly_candles: IndustryHierarchyView["candles"];
  monthly_candles: IndustryHierarchyView["candles"];
  stock_evidence: StockEvidence | null;
  known_gaps: string[];
}

export interface StockEvidence {
  instrument_id: string;
  instrument_name: string;
  as_of: string;
  fundamental: StockFundamentalEvidence | null;
  fundamental_history?: StockFundamentalEvidence[];
  shareholder_concentration: ShareholderConcentrationEvidence;
  shareholder_concentration_history?: ShareholderConcentrationEvidence[];
  known_gaps: string[];
}

export interface StockFundamentalEvidence {
  market_date: string;
  available_at: string;
  latest_close: number;
  percent_change: number | null;
  turnover_rate: number | null;
  price_earnings_ttm: number | null;
  price_book: number | null;
  total_market_value_cny: number | null;
  circulating_market_value_cny: number | null;
  amount_cny: number | null;
}

export interface ShareholderConcentrationEvidence {
  status: "ready" | "unavailable" | "insufficient_history";
  announced_on: string | null;
  reporting_period: string | null;
  available_at: string | null;
  holder_count: number | null;
  previous_holder_count: number | null;
  change_rate: number | null;
  direction: "concentrating" | "dispersing" | "unchanged" | null;
  consecutive_periods: number;
  observation_age_days: number | null;
  known_gaps: string[];
}

export const quadrantLabels: Record<Quadrant, string> = {
  leading: "强势领先",
  weakening: "强势降温",
  lagging: "弱势落后",
  improving: "弱势改善",
};
