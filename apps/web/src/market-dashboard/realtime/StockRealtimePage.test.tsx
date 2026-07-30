import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StockRealtimePage } from "./StockRealtimePage";

let mockState: "current" | "stale" | "disconnected" = "current";

vi.mock("../marketDashboardClient", () => ({
  fetchMarketWatchlist: vi.fn(async () => ["000001.SZ"]),
  fetchRealtimeInstruments: vi.fn(),
  saveMarketWatchlist: vi.fn(async (values: string[]) => values),
}));

vi.mock("./useRealtimeInstruments", () => ({
  useRealtimeInstruments: () => ({
    message: null,
    projection: {
      projection_id: `sha256:${"a".repeat(64)}`,
      provider: "miniqmt",
      session_id: `sha256:${"b".repeat(64)}`,
      state: mockState,
      as_of: "2026-07-30T10:00:00+08:00",
      market_date: "2026-07-30",
      quotes: [{
        instrument_id: "000001.SZ",
        instrument_name: "平安银行",
        instrument_type: "stock",
        industry_code: "801780.SI",
        market_time_ms: 1,
        received_at: "2026-07-30T10:00:00+08:00",
        last_price: 11.28,
        previous_close: 11.20,
        change_percent: 0.71,
        open_price: 11.21,
        high_price: 11.30,
        low_price: 11.18,
        volume: 1_000,
        amount: 11_280,
        upper_limit: 12.32,
        lower_limit: 10.08,
        stock_status: 0,
        status_label: "正常交易",
        bids: [],
        asks: [],
      }],
      open_minutes: [],
      known_gaps: [],
    },
  }),
}));

describe("StockRealtimePage business language", () => {
  afterEach(() => cleanup());

  it.each([
    ["current", "正在更新"],
    ["stale", "更新延迟"],
    ["disconnected", "实时连接中断"],
  ] as const)("renders %s through the shared accessible business label", (state, label) => {
    mockState = state;
    render(<StockRealtimePage />);

    expect(screen.getByLabelText(`实时行情状态：${label} · 1 只`)).toBeVisible();
    expect(screen.queryByText(`${state} · 1 只`)).not.toBeInTheDocument();
  });
});
