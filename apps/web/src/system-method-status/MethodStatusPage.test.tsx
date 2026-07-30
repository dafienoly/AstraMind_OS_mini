import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MarketModelStatusProjection } from "../market-dashboard/model-evidence/types";
import { MethodStatusPage } from "./MethodStatusPage";

const originalFetch = globalThis.fetch;

describe("MethodStatusPage", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async () => response(statusFixture()));
  });

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  it("selects all five families and explains fallback, blocked, pending and active states", async () => {
    render(<MethodStatusPage />);

    const index = await screen.findByRole("complementary", { name: "五类模型索引" });
    expect(within(index).getAllByRole("button")).toHaveLength(5);
    expect(screen.getByRole("region", { name: "行业热力方法状态" }))
      .toHaveAttribute("data-state", "fallback_v1");
    expect(screen.getAllByText("生产训练功能尚未接通，当前使用规则模型").length)
      .toBeGreaterThan(0);

    fireEvent.click(within(index).getByRole("button", { name: /相对轮动/ }));
    const rotation = screen.getByRole("region", { name: "相对轮动方法状态" });
    expect(rotation).toHaveAttribute("data-state", "unvalidated_v2");
    expect(rotation).toHaveTextContent("V2 已发布，样本外证据待完成");
    expect(screen.getByLabelText("样本外证据：当前待通过")).toBeVisible();

    fireEvent.click(within(index).getByRole("button", { name: /生命周期/ }));
    expect(screen.getByRole("region", { name: "生命周期方法状态" }))
      .toHaveTextContent("模型状态受阻，不能视为可用");
    expect(screen.getByLabelText("数据门：当前待通过")).toBeVisible();

    fireEvent.click(within(index).getByRole("button", { name: /行业内研究顺序/ }));
    expect(screen.getByRole("region", { name: "行业内研究顺序方法状态" }))
      .toHaveAttribute("data-state", "active_v2");
    expect(screen.getByRole("region", { name: "行业内研究顺序方法状态" }))
      .toHaveTextContent("学习模型 V2 已只读激活");
    expect(screen.getByLabelText("只读激活：已有发布记录")).toBeVisible();

    fireEvent.click(within(index).getByRole("button", { name: /ETF 轮动/ }));
    expect(screen.getByRole("region", { name: "ETF 轮动方法状态" }))
      .toHaveAttribute("data-tone", "danger");
    expect(screen.getByRole("region", { name: "ETF 轮动方法状态" }))
      .toHaveTextContent("模型制品损坏或输入版本不兼容");
  });

  it("keeps unpublished time fields explicit and raw identities folded", async () => {
    render(<MethodStatusPage />);
    await screen.findByRole("region", { name: "行业热力方法状态" });

    expect(screen.getAllByText("尚无已发布记录").length).toBeGreaterThanOrEqual(3);
    const details = screen.getByLabelText("技术详情");
    expect(details).not.toHaveAttribute("open");
    fireEvent.click(within(details).getByText("技术详情"));
    expect(details).toHaveAttribute("open");
    expect(screen.getByText(`sha256:${"b".repeat(64)}`)).toBeInTheDocument();
    expect(screen.getByText("fallback_v1")).toBeInTheDocument();
    expect(screen.getByText("production_pipeline_unavailable")).toBeInTheDocument();
  });

  it("preserves the last successful projection and marks a failed refresh", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(response(statusFixture()))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));
    globalThis.fetch = fetch;
    render(<MethodStatusPage />);
    await screen.findByRole("region", { name: "行业热力方法状态" });

    fireEvent.click(screen.getByRole("button", { name: "刷新状态投影" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "仍显示上一次成功投影",
    );
    expect(screen.getByRole("region", { name: "行业热力方法状态" })).toBeVisible();
  });

  it("fails closed for empty, disconnected and readonly-boundary responses", async () => {
    globalThis.fetch = vi.fn(async () => response({ ...statusFixture(), models: [] }));
    const { unmount } = render(<MethodStatusPage />);
    expect(await screen.findByRole("heading", { name: "尚无完整发布记录" })).toBeVisible();
    unmount();

    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const disconnected = render(<MethodStatusPage />);
    expect(await screen.findByRole("heading", { name: "本地状态服务已断开" })).toBeVisible();
    disconnected.unmount();

    globalThis.fetch = vi.fn(async () => response({
      ...statusFixture(),
      broker_actions_allowed: true,
    }));
    const readonlyBoundary = render(<MethodStatusPage />);
    expect(await screen.findByRole("heading", { name: "状态已失败关闭" })).toBeVisible();
    readonlyBoundary.unmount();

    const malformed = statusFixture();
    globalThis.fetch = vi.fn(async () => response({
      ...malformed,
      models: malformed.models.map((item, index) => (
        index === 0 ? { ...item, state: "mystery_state" } : item
      )),
    }));
    render(<MethodStatusPage />);
    expect(await screen.findByText("模型状态内容损坏，状态已失败关闭")).toBeVisible();
  });

  it("does not expose model governance or trading controls", async () => {
    render(<MethodStatusPage />);
    await screen.findByRole("region", { name: "行业热力方法状态" });

    for (const label of ["立即训练", "强制激活", "晋级策略", "下单", "Paper", "Live"]) {
      expect(screen.queryByRole("button", { name: label })).not.toBeInTheDocument();
    }
  });
});

function statusFixture(): MarketModelStatusProjection {
  return {
    status_id: `sha256:${"b".repeat(64)}`,
    as_of: "2026-07-30T10:15:00+08:00",
    models: [
      model("industry_heat", "行业热力", "fallback_v1", [
        "production_pipeline_unavailable",
      ]),
      model("industry_rotation", "相对轮动", "unvalidated_v2", [], {
        manifest_id: "market-model-manifest:rotation",
        evidence_bundle_id: "market-model-evidence:rotation",
        evidence_state: "unvalidated",
        effective_at: "2026-07-30T09:30:00+08:00",
        method_version: "rotation-forecast-hgb-v2.0.0",
      }),
      model("industry_lifecycle", "生命周期结构", "blocked", ["training_data_blocked"]),
      model("industry_research_ranking", "行业内研究顺序", "active_v2", [], {
        manifest_id: "market-model-manifest:ranking",
        evidence_bundle_id: "market-model-evidence:ranking",
        evidence_state: "supported",
        effective_at: "2026-07-30T09:45:00+08:00",
        method_version: "industry-research-ranking-hgb-v2.0.0",
      }),
      model("etf_rotation", "ETF 轮动", "fallback_v1", ["artifact_incompatible"]),
    ],
    known_gaps: [],
    broker_actions_allowed: false,
  };
}

function model(
  family: MarketModelStatusProjection["models"][number]["model_family"],
  displayName: string,
  state: MarketModelStatusProjection["models"][number]["state"],
  reasonCodes: string[],
  overrides: Partial<MarketModelStatusProjection["models"][number]> = {},
) {
  const fallback = `${family}-v1.0.0`;
  return {
    model_family: family,
    display_name: displayName,
    state,
    method_version: fallback,
    fallback_method_version: fallback,
    manifest_id: null,
    evidence_bundle_id: null,
    evidence_state: "blocked" as const,
    effective_at: null,
    reason_codes: reasonCodes,
    broker_actions_allowed: false as const,
    ...overrides,
  };
}

function response(value: object) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
