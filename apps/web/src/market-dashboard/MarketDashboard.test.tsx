import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketDashboard } from "./MarketDashboard";
import { fallbackModelStatus } from "./model-evidence/testSupport";
import { FakeEventSource, realtimeProjection } from "./realtimeTestSupport";
import type {
  IndustryLifecycleProjection,
  IndustryResearchRankingSnapshot,
  MarketDashboardProjection,
} from "./types";

const originalFetch = globalThis.fetch;
const originalEventSource = globalThis.EventSource;

describe("MarketDashboard", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    globalThis.EventSource = FakeEventSource as unknown as typeof EventSource;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => new Response(
      JSON.stringify(String(input).includes("/api/market/model-status")
        ? fallbackModelStatus()
        : String(input).includes("/api/market/realtime")
        ? realtimeProjection()
        : projection()),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
  });

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
    globalThis.EventSource = originalEventSource;
  });

  it("renders real overview evidence and switches broad index locally", async () => {
    render(<MarketDashboard view="overview" />);

    expect(await screen.findByRole("heading", { name: "沪深300" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /上证指数/ }));

    expect(screen.getByRole("heading", { name: "上证指数" })).toBeInTheDocument();
    expect(screen.getByText("3000 ↑ / 1900 ↓")).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it("renders all 31 industries and updates the inspector without refetching", async () => {
    render(<MarketDashboard view="heatmap" />);

    expect(await screen.findByRole("heading", { name: "行业结构热力" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /行业\d+/ })).toHaveLength(31);
    fireEvent.click(screen.getByRole("button", { name: /行业31/ }));

    expect(screen.getByRole("heading", { name: "行业31" })).toBeInTheDocument();
    expect(screen.getByText("31 / 31 行业 · 2026-07-28")).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "行业热力方法与证据" }))
      .toHaveAttribute("data-state", "fallback_v1");
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
  });

  it("fails closed when the API reports a blocked projection", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => new Response(
      JSON.stringify(String(input).includes("/api/market/realtime")
        ? realtimeProjection()
        : { ...projection(), status: "blocked", known_gaps: ["missing_dataset"] }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    render(<MarketDashboard view="overview" />);

    expect(await screen.findByText("当前快照不能形成一致的大盘判断")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "沪深300" })).not.toBeInTheDocument();
  });

  it("refreshes the bounded projection only when requested", async () => {
    render(<MarketDashboard view="overview" />);
    const refresh = await screen.findByRole("button", { name: "刷新快照" });
    fireEvent.click(refresh);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(3));
  });

  it("distinguishes an empty snapshot from a service error", async () => {
    globalThis.fetch = vi.fn(async () => new Response("", { status: 404 }));
    const view = render(<MarketDashboard view="overview" />);

    expect(await screen.findByRole("heading", { name: "尚无可展示的市场快照" }))
      .toBeInTheDocument();

    view.unmount();
    globalThis.fetch = vi.fn(async () => new Response("", { status: 503 }));
    render(<MarketDashboard view="overview" />);

    expect(await screen.findByRole("heading", { name: "市场服务不可用" }))
      .toBeInTheDocument();
  });

  it("labels stale evidence without hiding the bounded projection", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => new Response(
      JSON.stringify(String(input).includes("/api/market/realtime")
        ? realtimeProjection()
        : { ...projection(), status: "stale" }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
    render(<MarketDashboard view="overview" />);

    expect(await screen.findByText(/2026-07-28 已陈旧/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "沪深300" })).toBeInTheDocument();
  });

  it("renders the lifecycle map and keeps every industry in the readable index", async () => {
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/api/market/model-status")
        ? fallbackModelStatus()
        : url.includes("/api/market/realtime")
        ? realtimeProjection()
        : url.includes("industry-lifecycle")
        ? lifecycle()
        : url.includes("industry-ranking") ? ranking(url) : projection();
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    render(<MarketDashboard view="lifecycle" />);

    expect(await screen.findByRole("img", { name: "行业生命周期结构地图" }))
      .toBeInTheDocument();
    const index = screen.getByRole("complementary", { name: "生命周期行业索引" });
    expect(within(index).getAllByRole("button")).toHaveLength(31);
    fireEvent.click(within(index).getByRole("button", { name: /行业31/ }));

    expect(screen.getByRole("heading", { name: "行业31 · 方向未明", level: 1 }))
      .toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "行业31 · 方向未明", level: 2 }))
      .toBeInTheDocument();
    expect(screen.getByText("优先研究")).toBeInTheDocument();
    expect(globalThis.fetch).toHaveBeenCalledTimes(7);
  });

  it("applies SSE updates and closes the stream on unmount", async () => {
    const view = render(<MarketDashboard view="overview" />);
    expect(await screen.findByText("CURRENT · 正在更新")).toBeInTheDocument();
    expect(screen.getByText("3200 ↑ / 1800 ↓ / 100 —")).toBeInTheDocument();

    act(() => FakeEventSource.instances[0]?.emit(
      "market",
      { ...realtimeProjection(), advancing: 3210, declining: 1790 },
    ));

    expect(screen.getByText("3210 ↑ / 1790 ↓ / 100 —")).toBeInTheDocument();
    view.unmount();
    expect(FakeEventSource.instances[0]?.closed).toBe(true);
  });
});

function projection(): MarketDashboardProjection {
  const indexes = [
    ["000001.SH", "上证指数"],
    ["399001.SZ", "深证成指"],
    ["399006.SZ", "创业板指"],
    ["000688.SH", "科创50"],
    ["000300.SH", "沪深300"],
    ["000852.SH", "中证1000"],
  ].map(([instrument_id, instrument_name], index) => ({
    instrument_id,
    instrument_name,
    latest_trade_date: "2026-07-28",
    latest_close: 3000 + index,
    change: 10,
    percent_change: 0.5,
    return_20d: 0.03,
    drawdown_250d: -0.04,
    candles: Array.from({ length: 30 }, (_, offset) => ({
      trade_date: `2026-06-${String(offset + 1).padStart(2, "0")}`,
      open: 3000 + offset,
      high: 3010 + offset,
      low: 2990 + offset,
      close: 3005 + offset,
      volume_lots: 100_000 + offset,
      amount_cny: 300_000_000 + offset,
    })),
  }));
  const industries = Array.from({ length: 31 }, (_, index) => ({
    industry_code: `801${String(index + 1).padStart(3, "0")}.SI`,
    industry_name: `行业${index + 1}`,
    trade_date: "2026-07-28",
    percent_change: index / 10,
    relative_strength: index / 10 - 1.5,
    breadth_ratio: 0.6,
    advancing: 12,
    declining: 8,
    member_count: 20,
    covered_member_count: 20,
    coverage_ratio: 1,
    amount_change_20d: 0.1,
    volatility_20d: 1.2,
    price_earnings: 20,
    price_book: 2,
    leading_instrument_id: "000001.SZ",
    leading_instrument_name: "领先股份",
    leading_percent_change: 3.2,
    known_gaps: [],
  }));
  return {
    status: "ready",
    data_snapshot_id: `snapshot:sha256:${"1".repeat(64)}`,
    as_of: "2026-07-29T02:00:00Z",
    evidence_cutoff: "2026-07-28",
    projection_version: "market-dashboard-v1.0.0",
    selected_index_id: "000300.SH",
    indexes,
    breadth: {
      advancing: 3000,
      declining: 1900,
      unchanged: 100,
      advance_ratio: 0.6,
      new_high_250d: 88,
      new_low_250d: 12,
      upper_limit_locked: 70,
      lower_limit_locked: 3,
    },
    liquidity: {
      amount_cny: 1_300_000_000_000,
      amount_change_20d: 0.12,
      amount_percentile_250d: 0.8,
    },
    regime: {
      state: "strong",
      label: "价格与参与同步增强",
      confidence: 0.77,
      definition_version: "market-regime-breadth-price-v1.0.0",
      observations: ["沪深300近20日 +3.00%"],
    },
    industries,
    known_gaps: [],
  };
}

function ranking(url: string): IndustryResearchRankingSnapshot {
  const code = new URL(url).searchParams.get("industry_code") ?? "801001.SI";
  const number = Number(code.slice(3, 6));
  const row = {
    instrument_id: "000001.SZ",
    instrument_name: "研究股份",
    membership_effective_as_of: "2021-01-01",
    overall_priority: 76.2,
    event_sentiment_score: 72,
    technical_volume_score: 81,
    fundamental_score: 68,
    risk_score: 31,
    reversal_repair_score: 18,
    coverage: 1,
    research_label: "优先研究" as const,
    evidence_cutoff: "2026-07-28",
    known_gaps: [],
  };
  const candles = Array.from({ length: 30 }, (_, offset) => ({
    trade_date: `2026-06-${String(offset + 1).padStart(2, "0")}`,
    open: 10 + offset,
    high: 11 + offset,
    low: 9 + offset,
    close: 10.5 + offset,
    volume_lots: 100_000,
    amount_cny: 10_000_000,
  }));
  return {
    status: "ready",
    ranking_snapshot_id: `ranking:sha256:${"2".repeat(64)}`,
    data_snapshot_id: `snapshot:sha256:${"1".repeat(64)}`,
    lifecycle_snapshot_id: `lifecycle:sha256:${"3".repeat(64)}`,
    as_of: "2026-07-29T02:00:00Z",
    evidence_cutoff: "2026-07-28",
    taxonomy: "SW",
    taxonomy_version: "SW2021",
    industry_code: code,
    industry_name: `行业${number}`,
    lifecycle_stage: number === 1 ? "强势扩散" : "方向未明",
    scoring_definition_version: "industry-research-priority-v1.0.0",
    member_count: 1,
    covered_member_count: 1,
    content_hash: `sha256:${"4".repeat(64)}`,
    rows: [row],
    selected_instrument_id: row.instrument_id,
    candles,
    weekly_candles: candles.slice(-8),
    monthly_candles: candles.slice(-3),
    known_gaps: [],
  };
}

function lifecycle(): IndustryLifecycleProjection {
  return {
    status: "ready",
    data_snapshot_id: `snapshot:sha256:${"1".repeat(64)}`,
    as_of: "2026-07-29T02:00:00Z",
    evidence_cutoff: "2026-07-28",
    taxonomy_version: "SW2021",
    method_version: "lifecycle-structure-v1.0.0",
    industries: Array.from({ length: 31 }, (_, index) => ({
      industry_code: `801${String(index + 1).padStart(3, "0")}.SI`,
      industry_name: `行业${index + 1}`,
      stage: index === 0 ? "强势扩散" : "方向未明",
      confidence: "high",
      strong_participation: 20 + index,
      low_participation: 40 - index,
      strong_change_5d: index / 2,
      low_change_5d: -index / 3,
      strong_peak_20d: 30 + index,
      strong_drawdown_20d: 10,
      amount_share_20d: 1 / 31,
      eligible_member_count: 30,
      valid_member_count: 28,
      coverage_ratio: 28 / 30,
      recently_transitioned: false,
      trajectory: [{
        trade_date: "2026-07-28",
        strong_participation: 20 + index,
        low_participation: 40 - index,
      }],
      known_gaps: [],
    })),
    known_gaps: [],
  };
}
