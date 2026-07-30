import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";

const proposalDir = "docs/ui/proposals/0013-method-status";

test("System method status explains five read-only lineages on desktop and narrow screens", async ({
  page,
}) => {
  await page.route("**/api/market/model-status", async (route) => {
    await route.fulfill({ json: statusFixture() });
  });
  mkdirSync(proposalDir, { recursive: true });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/system/method-status");
  await expect(page.getByRole("heading", { name: "当前为什么使用这个方法？" })).toBeVisible();
  const systemNav = page.getByRole("navigation", { name: "系统视图" });
  await expect(systemNav.getByRole("link")).toHaveCount(3);
  await expect(systemNav.getByRole("link", { name: "方法与状态" }))
    .toHaveAttribute("aria-current", "page");
  const modelIndex = page.getByRole("complementary", { name: "五类模型索引" });
  await expect(modelIndex.getByRole("button")).toHaveCount(5);
  await expect(page.getByRole("region", { name: "行业热力方法状态" }))
    .toHaveAttribute("data-state", "fallback_v1");
  await modelIndex.getByRole("button", { name: /相对轮动/ }).click();
  await expect(page.getByRole("region", { name: "相对轮动方法状态" }))
    .toContainText("V2 已发布，样本外证据待完成");
  await modelIndex.getByRole("button", { name: /ETF 轮动/ }).click();
  await expect(page.getByRole("region", { name: "ETF 轮动方法状态" }))
    .toContainText("模型制品损坏或输入版本不兼容");
  await expect(page.getByRole("button", { name: /立即训练|强制激活|晋级策略|下单/ }))
    .toHaveCount(0);
  await modelIndex.getByRole("button", { name: /行业热力/ }).click();
  await page.screenshot({
    path: `${proposalDir}/actual-desktop-1440x1000.png`,
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole("region", { name: "当前模型摘要" })).toBeVisible();
  await expect(modelIndex).toBeVisible();
  await expect(page.getByRole("region", { name: "方法谱系尺" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(390);
  await page.screenshot({
    path: `${proposalDir}/actual-mobile-390x844.png`,
    fullPage: true,
  });
});

function statusFixture() {
  const model = (
    model_family: string,
    display_name: string,
    state: string,
    method_version: string,
    reason_codes: string[],
    evidence_state = "blocked",
  ) => ({
    model_family,
    display_name,
    state,
    method_version,
    fallback_method_version: `${model_family}-v1.0.0`,
    manifest_id: state === "unvalidated_v2" ? `manifest:${model_family}` : null,
    evidence_bundle_id: state === "unvalidated_v2" ? `evidence:${model_family}` : null,
    evidence_state,
    effective_at: state === "unvalidated_v2" ? "2026-07-30T09:30:00+08:00" : null,
    reason_codes,
    broker_actions_allowed: false,
  });
  return {
    status_id: `sha256:${"c".repeat(64)}`,
    as_of: "2026-07-30T10:15:00+08:00",
    models: [
      model(
        "industry_heat",
        "行业热力",
        "fallback_v1",
        "industry-heat-v1.0.0",
        ["production_pipeline_unavailable"],
      ),
      model(
        "industry_rotation",
        "相对轮动",
        "unvalidated_v2",
        "rotation-forecast-hgb-v2.0.0",
        [],
        "unvalidated",
      ),
      model(
        "industry_lifecycle",
        "生命周期结构",
        "blocked",
        "industry-lifecycle-v1.0.0",
        ["training_data_blocked"],
      ),
      model(
        "industry_research_ranking",
        "行业内研究顺序",
        "fallback_v1",
        "industry-research-priority-v1.0.0",
        ["trained_evidence_insufficient"],
      ),
      model(
        "etf_rotation",
        "ETF 轮动",
        "fallback_v1",
        "etf-rotation-research-v1.0.0",
        ["artifact_incompatible"],
      ),
    ],
    known_gaps: [],
    broker_actions_allowed: false,
  };
}
