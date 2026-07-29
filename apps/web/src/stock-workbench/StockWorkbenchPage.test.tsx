import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StockWorkbenchPage } from "./StockWorkbenchPage";
import type { StockWorkbenchProjection } from "./types";

vi.mock("../market-dashboard/realtime/useRealtimeInstruments", () => ({
  useRealtimeInstrumentDetail: () => ({
    state: "disconnected",
    quote: null,
    minutes: [],
  }),
}));

const originalFetch = globalThis.fetch;

describe("StockWorkbenchPage business language", () => {
  beforeEach(() => {
    window.history.replaceState(
      null,
      "",
      "/stocks/000001.SZ?origin=watchlist&mode=completed&return_target=market_stocks",
    );
    globalThis.fetch = vi.fn(async () => new Response(
      JSON.stringify(projection()),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
  });

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  it("keeps provider, hash and gap codes out of the primary evidence panels", async () => {
    render(<StockWorkbenchPage />);

    expect(await screen.findByRole("heading", { level: 1, name: /平安银行/ })).toBeVisible();
    expect(screen.getByText("Tushare 历史行情")).toBeVisible();
    expect(screen.getByText(
      /缺少当时可知的历史行业归属，暂不能进行严格历史验证/,
    )).toBeVisible();
    const details = screen.getByLabelText("技术详情");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByText("tushare")).not.toBeVisible();
    expect(screen.getByText(projection().content_identity)).not.toBeVisible();
    expect(screen.getByText("historical_membership_not_then_known")).not.toBeVisible();
  });
});

function projection(): StockWorkbenchProjection {
  const contentIdentity = `sha256:${"b".repeat(64)}`;
  return {
    focus: {
      focus_id: `sha256:${"a".repeat(64)}`,
      instrument_id: "000001.SZ",
      origin: "watchlist",
      as_of: "2026-07-29",
      data_snapshot_id: `snapshot:sha256:${"c".repeat(64)}`,
      industry_code: "801780.SI",
      cohort_id: null,
      strategy_version_id: null,
      portfolio_snapshot_id: null,
      attention_case_id: null,
      mode: "completed",
      return_target: "market_stocks",
      created_at: "2026-07-29T18:00:00+08:00",
    },
    instrument_identity: {
      instrument_id: "000001.SZ",
      instrument_name: "平安银行",
      exchange: "SZ",
      market: "主板",
      risk_status: null,
      is_special_treatment: false,
    },
    completed_market_evidence: {
      evidence: {
        state: "ready",
        as_of: "2026-07-29",
        provider: "tushare",
        content_identity: contentIdentity,
        known_gaps: [],
      },
      daily: [],
      weekly: [],
      monthly: [],
    },
    realtime_market_overlay: null,
    industry_context: {
      evidence: {
        state: "blocked",
        as_of: "2026-07-29",
        provider: "tushare",
        content_identity: contentIdentity,
        known_gaps: ["historical_membership_not_then_known"],
      },
      taxonomy: "SW",
      taxonomy_version: "SW2021",
      l1_code: "801780.SI",
      l1_name: "银行",
      l2_code: null,
      l2_name: null,
    },
    stock_evidence: {
      instrument_id: "000001.SZ",
      instrument_name: "平安银行",
      as_of: "2026-07-29",
      fundamental: null,
      shareholder_concentration: {
        status: "unavailable",
        announced_on: null,
        reporting_period: null,
        available_at: null,
        holder_count: null,
        previous_holder_count: null,
        change_rate: null,
        direction: null,
        consecutive_periods: 0,
        observation_age_days: null,
        known_gaps: ["shareholder_count_not_in_snapshot"],
      },
      known_gaps: ["historical_membership_not_then_known"],
    },
    content_identity: contentIdentity,
    known_gaps: ["historical_membership_not_then_known"],
  };
}
