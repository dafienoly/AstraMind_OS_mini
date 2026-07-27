import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";

test("development diagnostic reports the API and protected boundary", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "产品界面尚未实现" })).toBeVisible();
  await expect(page.getByText(/API 状态：.*已连接.*券商关闭/)).toBeVisible();
});

test("UI Lab inspects a point-in-time chart range without future data", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/dev/ui-lab");
  await expect(page.getByRole("heading", { name: "统一价格检查器" })).toBeVisible();
  await expect(page.getByText("未来数据已隔离")).toBeVisible();
  await expect(page.locator("canvas").first()).toBeVisible();
  await expect(page.locator(".chart-shell")).toHaveAttribute("data-max-date", /2025-05/);

  await page.getByRole("button", { name: "周线" }).click();
  await expect(page.getByRole("button", { name: "周线" })).toHaveClass(/active/);
  const start = page.getByRole("slider", { name: "区间起点" });
  await start.focus();
  await start.press("ArrowRight");
  await expect(page.getByTestId("dual-range")).toBeVisible();

  const chart = page.locator(".chart-canvas");
  const box = await chart.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.35);
  }
  await expect(page.locator(".chart-legend strong")).not.toHaveText("移动指针查看");

  mkdirSync("var/evidence", { recursive: true });
  await page.screenshot({
    path: "var/evidence/wp-0003-ui-lab.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "统一价格检查器" })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.screenshot({
    path: "var/evidence/wp-0003-ui-lab-mobile.png",
    fullPage: true,
  });
});
