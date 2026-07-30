import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RealtimePulse } from "./RealtimePulse";
import { realtimeProjection } from "./realtimeTestSupport";
import type { RealtimeOperationalState } from "./realtimeTypes";
import { effectiveState, type RealtimeMarketView } from "./useRealtimeMarket";

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

  it("keeps session identities out of the primary status surface", () => {
    const projection = realtimeProjection();
    render(<RealtimePulse view={view("updating")} />);

    expect(screen.getByText("实时会话已建立")).toBeVisible();
    expect(screen.getByLabelText("技术详情")).not.toHaveAttribute("open");
    expect(screen.getByText(projection.session_id)).not.toBeVisible();
    expect(screen.getByText(projection.projection_id)).not.toBeVisible();
  });

  it("keeps transport unknown while the first projection is loading", () => {
    render(<RealtimePulse view={{
      phase: "loading",
      connection: "connecting",
      projection: null,
      message: null,
      effectiveState: "disconnected",
    }} />);

    const pulse = screen.getByRole("region", { name: "盘中会话脉冲" });
    expect(pulse).toHaveAttribute("data-state", "unknown");
    expect(screen.getByText("正在连接")).toBeInTheDocument();
    expect(screen.getByText("传输").parentElement).toHaveTextContent("待确认");
    expect(screen.queryByText("实时连接中断")).not.toBeInTheDocument();
  });

  it("does not fold a non-streaming market phase back into stale", () => {
    const projection = {
      ...realtimeProjection(),
      state: "current" as const,
      market_session: "lunch_break" as const,
      operational_state: "lunch_break" as const,
    };

    expect(effectiveState(projection)).toBe("current");
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
