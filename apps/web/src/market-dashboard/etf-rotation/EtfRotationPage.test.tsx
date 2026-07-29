import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { EtfRotationProjection } from "../types";
import { EtfRotationPage } from "./EtfRotationPage";
import { fallbackModelStatus } from "../model-evidence/testSupport";

const originalFetch = globalThis.fetch;

describe("EtfRotationPage", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/market?tab=etf");
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => new Response(
      JSON.stringify(String(input).includes("/api/market/model-status")
        ? fallbackModelStatus()
        : projection()),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
  });

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  it("renders the approved funnel, blocked evidence and cash-only target", async () => {
    render(<EtfRotationPage />);

    expect(await screen.findByRole("heading", {
      name: "方向到 ETF，再核验价格结构",
    })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "ETF 方向漏斗" })).toBeInTheDocument();
    expect(screen.getByText("研究门禁关闭")).toBeInTheDocument();
    expect(screen.getByText("决策截止 2026-07-28")).toBeInTheDocument();
    expect(screen.getByText("ETF 日线最新 2026-06-30")).toBeInTheDocument();
    expect(screen.getByText("MiniQMT 实时：连接断开")).toBeInTheDocument();
    expect(screen.getByText("现金 100%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "公共组合目标未授权" })).toBeDisabled();
    expect(screen.getByText("候选冻结历史回放不可用于晋级")).toBeInTheDocument();
  });

  it("switches ETF price evidence and refreshes the selected intraday detail", async () => {
    render(<EtfRotationPage />);
    await screen.findByRole("heading", { name: "农业ETF" });

    fireEvent.click(screen.getByRole("button", { name: /化工ETF/ }));
    expect(screen.getByRole("heading", { name: "化工ETF" })).toBeInTheDocument();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(4));

    fireEvent.click(screen.getByRole("button", { name: "刷新快照" }));
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(5));
  });

  it("translates provider mapping tiers into user-facing evidence", async () => {
    const value = projection();
    value.candidates[0] = {
      ...value.candidates[0],
      mapping_tier: "theme_context",
      state: "context_only",
      rejection_reasons: ["mapping_tier:theme_context"],
    };
    globalThis.fetch = vi.fn(async () => new Response(
      JSON.stringify(value),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));

    render(<EtfRotationPage />);

    expect(await screen.findByText(
      "主题相关 ETF，并非行业精确映射，只作背景参考",
    )).toBeInTheDocument();
    expect(screen.queryByText("mapping_tier:theme_context")).not.toBeInTheDocument();
  });
});

function projection(): EtfRotationProjection {
  const candidates = [
    ["801010.SI", "农林牧渔", "159825.SZ", "农业ETF"],
    ["801030.SI", "基础化工", "516020.SH", "化工ETF"],
  ].map(([industry_code, industry_name, etf_code, etf_name], index) => ({
    industry_code,
    industry_name,
    lifecycle_stage: "强势扩散",
    lifecycle_confidence: "high",
    etf_code,
    etf_name,
    mapping_tier: "exact",
    state: "unavailable" as const,
    overall_score: 75 - index,
    lifecycle_score: 100,
    relative_strength_score: 55,
    price_structure_score: 100,
    liquidity_score: 80,
    return_20d: 0.08,
    return_60d: 0.12,
    median_amount_20d_cny: 100_000_000,
    latest_size_cny: 2_000_000_000,
    spread_proxy_bps: 12,
    spread_evidence_kind: "corwin_schultz_ohlc_proxy" as const,
    tracking_error_60d: 0.06,
    tracking_evidence_kind: "sw_l1_exposure_proxy" as const,
    price_conclusion: "趋势确认，未过热",
    rejection_reasons: ["mapping_not_effective_at_as_of"],
    candles: candles(),
    weekly_candles: candles(),
    monthly_candles: candles(),
  }));
  return {
    status: "blocked",
    rotation_snapshot_id: "etf-rotation:test",
    data_snapshot_id: "snapshot:test",
    as_of: "2026-07-29T08:44:00Z",
    evidence_cutoff: "2026-07-28",
    strategy_version: "etf-rotation-research-v1.0.0",
    mapping_version: "sw2021-l1-etf-mapping-v1.0.0",
    spread_proxy_threshold_bps: 35,
    tracking_proxy_threshold: 0.12,
    funnel: {
      industry_count: 31,
      exact_mapping_count: 0,
      foundation_count: 0,
      evidence_gate_count: 0,
      eligible_count: 0,
    },
    candidates,
    target_draft: {
      status: "cash_only",
      weights: [],
      cash_weight: 1,
      max_gross_weight: 0.6,
      current_weights_observed: false,
      portfolio_target_created: false,
      order_plan_created: false,
      known_gaps: ["current_holdings_not_connected"],
    },
    replay: {
      status: "candidate_frozen",
      evidence_label: "候选冻结历史回放不可用于晋级",
      start_date: "2021-01-04",
      end_date: "2026-07-28",
      decision_count: 0,
      total_return: null,
      max_drawdown: null,
      turnover: null,
      estimated_cost_cny: null,
      next_open_execution: true,
      initial_research_cash_cny: 50_000,
      commission_rate: 0.00005,
      minimum_commission_cny: 5,
      slippage_bps_per_side: 20,
      stamp_duty_rate: 0,
      promotion_evidence_eligible: false,
      known_gaps: ["performance_metrics_withheld"],
    },
    selected_etf_code: "159825.SZ",
    known_gaps: ["etf_mapping_not_effective_at_snapshot_as_of"],
    broker_actions_allowed: false,
  };
}

function candles() {
  return Array.from({ length: 30 }, (_, index) => ({
    trade_date: `2026-06-${String(index + 1).padStart(2, "0")}`,
    open: 2 + index / 100,
    high: 2.02 + index / 100,
    low: 1.98 + index / 100,
    close: 2.01 + index / 100,
    volume_lots: 1_000_000,
    amount_cny: 100_000_000,
  }));
}
