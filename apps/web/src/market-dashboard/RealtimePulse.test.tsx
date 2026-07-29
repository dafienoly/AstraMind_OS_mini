import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RealtimePulse } from "./RealtimePulse";
import { realtimeProjection } from "./realtimeTestSupport";
import type { RealtimeOperationalState } from "./realtimeTypes";
import type { RealtimeMarketView } from "./useRealtimeMarket";

describe("RealtimePulse market-session semantics", () => {
  afterEach(cleanup);

  it.each([
    ["update_delayed", "行情更新延迟"],
    ["pre_open", "开盘前 · 最近交易日数据最新"],
    ["lunch_break", "午间休市 · 上午行情已保存"],
    ["closed", "今日已收盘 · 日线数据最新"],
    ["non_trading_day", "市场休市 · 最近交易日数据最新"],
    ["disconnected", "实时连接中断"],
    ["daily_lagging", "日线数据待更新"],
    ["unknown", "行情状态待确认"],
  ] as const)("renders %s as business text", (state, label) => {
    render(<RealtimePulse view={view(state)} />);

    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

function view(state: RealtimeOperationalState): RealtimeMarketView {
  return {
    phase: "ready",
    connection: state === "disconnected" ? "disconnected" : "connected",
    projection: {
      ...realtimeProjection(),
      state: state === "disconnected" ? "disconnected" : "stale",
      operational_state: state,
    },
    message: null,
    effectiveState: state === "disconnected" ? "disconnected" : "stale",
  };
}
