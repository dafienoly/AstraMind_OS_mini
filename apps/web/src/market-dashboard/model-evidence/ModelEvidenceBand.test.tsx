import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ModelEvidenceBand } from "./ModelEvidenceBand";
import { fallbackModelStatus } from "./testSupport";

const originalFetch = globalThis.fetch;

describe("ModelEvidenceBand", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async () => new Response(
      JSON.stringify(fallbackModelStatus()),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ));
  });

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  it("shows accurate v1 fallback and does not enable unpublished predictions", async () => {
    render(<StrictMode><ModelEvidenceBand
        dataCutoff="2026-07-28"
        family="industry_heat"
        horizons={["未来 1 日", "未来 5 日"]}
      /></StrictMode>);

    const band = await screen.findByRole("region", { name: "行业热力方法与证据" });
    expect(band).toHaveAttribute("data-state", "fallback_v1");
    expect(screen.getByText("industry-heat-v1.0.0")).toBeInTheDocument();
    expect(screen.getByText(/学习模型尚未形成生产结果/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "未来 1 日" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "原始结构" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText(/训练截止 规则式 · 不适用/)).toBeInTheDocument();
  });

  it("reveals evidence identities and the read-only boundary", async () => {
    render(<ModelEvidenceBand
      dataCutoff="2026-07-28"
      family="etf_rotation"
      horizons={["未来 20 日"]}
    />);
    fireEvent.click(await screen.findByRole("button", { name: "查看方法" }));

    expect(screen.getByText("尚无支持性证据包")).toBeInTheDocument();
    expect(screen.getByText(/不创建组合、订单或券商动作/)).toBeInTheDocument();
    expect(screen.getAllByText(/真实 L1 价差已累计 0\/60/)).toHaveLength(2);
    expect(screen.getByLabelText("技术详情")).not.toHaveAttribute("open");
  });

  it("keeps the raw page usable and offers retry when status is unknown", async () => {
    globalThis.fetch = vi.fn(async () => new Response(null, { status: 503 }));
    render(<ModelEvidenceBand
      dataCutoff="2026-07-28"
      family="industry_rotation"
      horizons={["未来 5 日", "未来 20 日"]}
    />);

    expect(await screen.findByText("页面原始证据仍保持可读")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试模型状态" })).toBeInTheDocument();
  });

  it("does not expose a browser abort exception to the user", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("signal is aborted without reason");
    });
    render(<ModelEvidenceBand
      dataCutoff="2026-07-29"
      family="etf_rotation"
      horizons={["未来 20 日"]}
    />);

    expect(await screen.findByText("模型状态请求已中断，请重试")).toBeInTheDocument();
    expect(screen.queryByText("signal is aborted without reason")).not.toBeInTheDocument();
  });
});
