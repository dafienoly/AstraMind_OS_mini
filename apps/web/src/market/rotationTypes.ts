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
}

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
    neutral_band: number;
    confirmation_sessions: number;
  };
  taxonomy_version: string;
  industry_count: number;
  covered_industry_count: number;
  coverage_rule: string;
  date_range: [string, string];
  dates: string[];
  points: RotationPoint[];
  events: RotationEvent[];
  content_hash: string;
  known_gaps: string[];
}

export const quadrantLabels: Record<Quadrant, string> = {
  leading: "强势领先",
  weakening: "强势降温",
  lagging: "弱势落后",
  improving: "弱势改善",
};
