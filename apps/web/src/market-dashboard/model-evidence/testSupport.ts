import type { MarketModelStatusProjection } from "./types";

export function fallbackModelStatus(): MarketModelStatusProjection {
  return {
    status_id: `sha256:${"a".repeat(64)}`,
    as_of: "2026-07-29T14:00:00+08:00",
    models: [
      ["industry_heat", "行业热力", "industry-heat-v1.0.0"],
      ["industry_rotation", "相对轮动", "rotation-index-ew-v1.0.0"],
      ["industry_lifecycle", "生命周期结构", "lifecycle-structure-v1.0.0"],
      ["industry_research_ranking", "行业内研究顺序", "industry-research-priority-v1.0.0"],
      ["etf_rotation", "ETF 轮动", "etf-rotation-research-v1.0.0"],
    ].map(([model_family, display_name, method_version]) => ({
      model_family,
      display_name,
      state: "fallback_v1",
      method_version,
      fallback_method_version: method_version,
      manifest_id: null,
      evidence_bundle_id: null,
      evidence_state: "blocked",
      effective_at: null,
      reason_codes: model_family === "etf_rotation"
        ? ["official_benchmark_mapping_not_then_known", "l1_spread_sessions:0/60"]
        : ["v2_not_trained"],
      broker_actions_allowed: false,
    })),
    known_gaps: [],
    broker_actions_allowed: false,
  } as MarketModelStatusProjection;
}
