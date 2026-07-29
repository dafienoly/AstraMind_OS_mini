import type {
  StockInspectionMode,
  StockInspectionOrigin,
  StockReturnTarget,
} from "./types";

const origins = new Set<StockInspectionOrigin>([
  "watchlist",
  "industry_rotation",
  "industry_lifecycle",
  "industry_ranking",
  "strategy_candidate",
  "portfolio_holding",
  "attention_case",
]);
const modes = new Set<StockInspectionMode>([
  "current",
  "completed",
  "historical_replay",
  "sealed_evidence",
]);
const returnTargets = new Set<StockReturnTarget>([
  "market_stocks",
  "industry_rotation",
  "industry_lifecycle",
  "industry_ranking",
  "strategy_arena",
  "portfolio",
  "today",
]);

export type StockFocusRequest = {
  origin: StockInspectionOrigin;
  mode: StockInspectionMode;
  returnTarget: StockReturnTarget;
  dataSnapshotId?: string;
  asOf?: string;
  industryCode?: string;
};

export function readStockFocusRequest(): StockFocusRequest {
  const query = new URLSearchParams(window.location.search);
  return {
    origin: oneOf(query.get("origin"), origins, "watchlist"),
    mode: oneOf(query.get("mode"), modes, "current"),
    returnTarget: oneOf(query.get("return_target"), returnTargets, "market_stocks"),
    dataSnapshotId: query.get("data_snapshot_id") ?? undefined,
    asOf: query.get("as_of") ?? undefined,
    industryCode: query.get("industry_code") ?? undefined,
  };
}

export function stockWorkbenchHref(
  instrumentId: string,
  request: StockFocusRequest,
) {
  const query = new URLSearchParams({
    origin: request.origin,
    mode: request.mode,
    return_target: request.returnTarget,
  });
  if (request.dataSnapshotId) query.set("data_snapshot_id", request.dataSnapshotId);
  if (request.asOf) query.set("as_of", request.asOf);
  if (request.industryCode) query.set("industry_code", request.industryCode);
  return `/stocks/${encodeURIComponent(instrumentId)}?${query}`;
}

export function fallbackReturnHref(target: StockReturnTarget, industryCode?: string) {
  if (target === "industry_rotation") return "/market?tab=industries&view=rotation";
  if (target === "industry_lifecycle" || target === "industry_ranking") {
    const query = new URLSearchParams({ tab: "industries", view: "lifecycle" });
    if (industryCode) query.set("lifecycleIndustry", industryCode);
    return `/market?${query}`;
  }
  if (target === "strategy_arena") return "/strategy-arena";
  if (target === "portfolio") return "/portfolio";
  if (target === "today") return "/today";
  return "/market?tab=stocks";
}

function oneOf<T extends string>(
  value: string | null,
  values: Set<T>,
  fallback: T,
): T {
  return value && values.has(value as T) ? value as T : fallback;
}
