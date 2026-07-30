export type PrimaryDestination =
  | "today"
  | "market"
  | "strategy-arena"
  | "portfolio"
  | "system";

export type MarketDestination = "overview" | "stocks" | "industries" | "etf";
export type IndustryDestination = "heatmap" | "lifecycle" | "rotation";
export type SystemDestination = "data-jobs" | "method-status" | "execution-recovery";

export type RouteLoadPhase =
  | "navigating"
  | "loading_content"
  | "connecting_realtime"
  | "ready"
  | "error";

export type RouteLoadReport = {
  phase: RouteLoadPhase;
  label: string;
};

export type AppLocation = {
  pathname: string;
  search: string;
  key: string;
};
