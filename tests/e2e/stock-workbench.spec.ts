import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";

test("common stock workbench opens from one immutable snapshot", async ({ page }) => {
  test.setTimeout(30_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(
    "/stocks/600001.SH?origin=watchlist&mode=sealed_evidence"
      + "&return_target=market_stocks",
  );

  await expect(page.getByRole("heading", {
    level: 1,
    name: "合成股票01 600001.SH",
  })).toBeVisible();
  await expect(page.getByRole("region", { name: "证券行情检查器" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "一级导航" })).toHaveCount(1);
  await expect(page.getByRole("navigation", { name: "市场视图" })).toBeVisible();
  await expect(page.getByRole("button", { name: /买入|卖出|下单|撤单/ })).toHaveCount(0);
  mkdirSync("var/evidence", { recursive: true });
  await page.screenshot({
    path: "var/evidence/wp-0048-stock-workbench.png",
    fullPage: true,
  });
});
