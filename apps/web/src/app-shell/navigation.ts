import type {
  AppLocation,
  IndustryDestination,
  MarketDestination,
  PrimaryDestination,
} from "./types";

export const primaryNavigation: ReadonlyArray<{
  id: PrimaryDestination;
  label: string;
  href: string;
}> = [
  { id: "today", label: "今日", href: "/today" },
  { id: "market", label: "市场", href: "/market?tab=overview" },
  { id: "strategy-arena", label: "策略竞技场", href: "/strategy-arena" },
  { id: "portfolio", label: "组合", href: "/portfolio" },
  { id: "system", label: "系统", href: "/system" },
];

export const marketNavigation: ReadonlyArray<{
  id: MarketDestination;
  label: string;
  href: string;
}> = [
  { id: "overview", label: "大盘", href: "/market?tab=overview" },
  { id: "stocks", label: "个股观察", href: "/market?tab=stocks" },
  { id: "industries", label: "行业", href: "/market?tab=industries&view=heatmap" },
  { id: "etf", label: "ETF 轮动", href: "/market?tab=etf" },
];

export const industryNavigation: ReadonlyArray<{
  id: IndustryDestination;
  label: string;
  href: string;
}> = [
  { id: "heatmap", label: "行业热力", href: "/market?tab=industries&view=heatmap" },
  { id: "lifecycle", label: "生命周期结构", href: "/market?tab=industries&view=lifecycle" },
  { id: "rotation", label: "相对轮动", href: "/market?tab=industries&view=rotation" },
];

export function readLocation(): AppLocation {
  return {
    pathname: window.location.pathname,
    search: window.location.search,
    key: `${window.location.pathname}${window.location.search}`,
  };
}

export function primaryDestination(location: AppLocation): PrimaryDestination {
  if (location.pathname === "/today") return "today";
  if (location.pathname === "/portfolio" || location.pathname === "/execution") {
    return "portfolio";
  }
  if (location.pathname === "/system") return "system";
  if (location.pathname === "/strategy-arena") return "strategy-arena";
  if (location.pathname.startsWith("/stocks/")) {
    const origin = new URLSearchParams(location.search).get("origin");
    if (origin === "strategy_candidate") return "strategy-arena";
    if (origin === "portfolio_holding") return "portfolio";
    if (origin === "attention_case") return "today";
  }
  return "market";
}

export function marketDestination(location: AppLocation): MarketDestination {
  if (location.pathname.startsWith("/stocks/")) return "stocks";
  const tab = new URLSearchParams(location.search).get("tab");
  if (tab === "stocks" || tab === "industries" || tab === "etf") return tab;
  return "overview";
}

export function industryDestination(location: AppLocation): IndustryDestination {
  const view = new URLSearchParams(location.search).get("view");
  return view === "lifecycle" || view === "rotation" ? view : "heatmap";
}
