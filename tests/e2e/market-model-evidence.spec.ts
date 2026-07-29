import { expect, test } from "@playwright/test";

const proposalDir = "docs/ui/proposals/0012-market-model-evidence-overlay";

test("market model evidence band explains fallback on desktop", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/market?tab=industries&view=heatmap");

  const band = page.getByRole("region", { name: "行业热力方法与证据" });
  await expect(band).toBeVisible();
  await expect(band).toHaveAttribute("data-state", "fallback_v1");
  await expect(band.getByText("industry-heat-v1.0.0")).toBeVisible();
  await expect(band.getByText(/当前准确显示规则式 v1/)).toBeVisible();
  await expect(band.getByRole("button", { name: "原始结构" }))
    .toHaveAttribute("aria-pressed", "true");

  await band.getByRole("button", { name: "查看方法" }).click();
  await expect(band.getByText(/不创建组合、订单或券商动作/)).toBeVisible();
  await page.screenshot({ path: `${proposalDir}/actual-desktop-1440x1000.png` });
});

test("fallback identity stays ahead of controls on a narrow rotation view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/market?tab=industries&view=rotation");

  const band = page.getByRole("region", { name: "相对轮动方法与证据" });
  await expect(band).toBeVisible();
  await expect(band.getByText("rotation-index-ew-v1.0.0")).toBeVisible();
  await expect(band.getByText("已回退规则式 v1")).toBeVisible();
  await expect(band.getByRole("button", { name: "未来 5 日" })).toBeDisabled();
  await expect(band.getByRole("button", { name: "原始结构" }))
    .toHaveAttribute("aria-pressed", "true");

  await page.screenshot({ path: `${proposalDir}/actual-mobile-390x844.png` });
});
