import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";

test("ETF rotation renders restored candidates instead of an unavailable state", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/market?tab=etf");

  await expect(page.getByRole("heading", { name: "方向到 ETF，再核验价格结构" }))
    .toBeVisible();
  await expect(page.getByRole("region", { name: "ETF 方向漏斗" })).toBeVisible();
  await expect(page.getByText("ETF 研究不可用")).toHaveCount(0);
  await expect(page.locator(".etf-candidate").first()).toBeVisible();
  expect(await page.locator(".etf-candidate").count()).toBeGreaterThan(0);
  await expect(page.locator(".etf-status")).toContainText(/研究就绪|证据陈旧/);
  await expect(page.getByRole("button", { name: /提交|撤单|买入|卖出/ })).toHaveCount(0);

  mkdirSync("var/evidence", { recursive: true });
  await page.screenshot({
    path: "var/evidence/wp-0044-etf-rotation-restored.png",
    fullPage: true,
  });

  await page.locator(".etf-candidate").filter({ hasText: "纺织服饰" }).click();
  await expect(page.getByText(
    "主题相关 ETF，并非行业精确映射，只作背景参考",
  )).toBeVisible();
  await expect(page.getByText("mapping_tier:theme_context")).toHaveCount(0);
  await page.screenshot({
    path: "var/evidence/wp-0044-etf-theme-context.png",
    fullPage: true,
  });
});
