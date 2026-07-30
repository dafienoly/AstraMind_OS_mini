import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";

test("development diagnostic reports the API and protected boundary", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "本地量化交易工作台" })).toBeVisible();
  await expect(page.getByText(/API 状态：.*已连接.*券商关闭/)).toBeVisible();
});

test("system shows the committed data and decision chain without broker actions", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/system");
  await expect(page.getByRole("heading", { name: "只显示今天是否可运行" })).toBeVisible();
  await expect(page.getByRole("region", { name: "日常运行", exact: true })).toBeVisible();
  await expect(page.getByText(/· L1 31 \/ L2 124/)).toBeVisible();
  await expect(page.getByText(/· Shadow ready \/ Paper ready/)).toBeVisible();
  await expect(page.getByRole("region", { name: "日常运行异常收件箱" })).toBeVisible();
  await expect(page.getByRole("button", { name: /提交|撤单|买入|卖出/ })).toHaveCount(0);
  mkdirSync("var/evidence", { recursive: true });
  await page.screenshot({
    path: "var/evidence/wp-0032-system-daily-operations.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.screenshot({
    path: "var/evidence/wp-0032-system-daily-operations-mobile.png",
    fullPage: true,
  });
});

test("today consumes the same daily exception projection", async ({ page }) => {
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: "下一动作很明确" })).toBeVisible();
  await expect(page.getByRole("region", { name: "日常运行异常收件箱" })).toBeVisible();
  await expect(page.getByText("日度计划任务尚未安装")).toBeVisible();
  await expect(page.getByRole("button", { name: /提交|撤单|买入|卖出/ })).toHaveCount(0);
});

test("market overview and industry heat use one bounded projection per view", async ({ page }) => {
  test.setTimeout(120_000);
  let dashboardRequests = 0;
  let historyRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/market/dashboard")) dashboardRequests += 1;
    if (request.url().includes("/api/market/history/index/")) historyRequests += 1;
  });
  mkdirSync("var/evidence", { recursive: true });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/market?tab=overview");
  await expect(page.getByRole("heading", { name: "沪深300" })).toBeVisible();
  const realtimePulse = page.getByRole("region", { name: "盘中会话脉冲" });
  await expect(realtimePulse).toBeVisible();
  await expect(realtimePulse).toContainText(
    /CURRENT|STALE|DISCONNECTED|等待|不可用|连接/,
  );
  await expect(realtimePulse).toContainText("市场时间");
  await expect(realtimePulse).toContainText("接收时间");
  await expect(page.getByRole("region", { name: "宽基指数" }).getByRole("button"))
    .toHaveCount(6);
  await page.getByRole("button", { name: /上证指数/ }).click();
  await page.getByRole("button", { name: "近五年" }).click();
  await expect(page.getByText(/实际覆盖 .* · 快照和证据截止保持不变/)).toBeVisible();
  await page.getByRole("button", { name: "周线" }).click();
  await expect(page.getByRole("heading", { name: "上证指数" })).toBeVisible();
  expect(dashboardRequests).toBe(1);
  expect(historyRequests).toBeGreaterThanOrEqual(1);
  await page.screenshot({
    path: "var/evidence/wp-0045-realtime-market-overview.png",
    fullPage: true,
  });

  await page.goto("/market?tab=industries&view=heatmap");
  await expect(page.getByRole("heading", { name: "行业结构热力" })).toBeVisible();
  const industries = page.locator(".heat-grid button");
  await expect(industries).toHaveCount(31);
  await industries.nth(20).click();
  await expect(page.locator(".heat-inspector h2")).not.toBeEmpty();
  expect(dashboardRequests).toBe(2);
  await expect(page.getByRole("button", { name: /提交|撤单|买入|卖出/ })).toHaveCount(0);
  await page.screenshot({
    path: "var/evidence/wp-0045-realtime-industry-heatmap.png",
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.screenshot({
    path: "var/evidence/wp-0045-realtime-industry-heatmap-mobile.png",
    fullPage: true,
  });
  await page.goto("/market?tab=overview");
  await expect(page.getByRole("heading", { name: "沪深300" })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.screenshot({
    path: "var/evidence/wp-0045-realtime-market-overview-mobile.png",
    fullPage: true,
  });
});

test("industry lifecycle keeps the full index and one immutable snapshot", async ({ page }) => {
  test.setTimeout(120_000);
  let lifecycleRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/market/industry-lifecycle")) lifecycleRequests += 1;
  });
  mkdirSync("var/evidence", { recursive: true });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/market?tab=industries&view=lifecycle");
  await expect(page.getByRole("img", { name: "行业生命周期结构地图" }))
    .toBeVisible({ timeout: 30_000 });
  const index = page.getByRole("complementary", { name: "生命周期行业索引" });
  await expect(index.getByRole("button")).toHaveCount(31);
  await index.getByRole("button").nth(20).click();
  await expect(page.locator(".lifecycle-heading h1")).not.toBeEmpty();
  await expect(page.getByText("研究观察，不是买卖信号").last()).toBeVisible();
  const ranking = page.getByRole("region", { name: "行业内个股研究排序" });
  await expect(ranking).toBeVisible({ timeout: 30_000 });
  await expect(ranking.locator("tbody tr").first()).toBeVisible();
  await ranking.locator("tbody tr").nth(1).click();
  await expect(ranking.getByRole("button", { name: "周线" })).toBeVisible();
  await ranking.getByRole("button", { name: "周线" }).click();
  await expect(ranking.getByTestId("dual-range")).toBeVisible();
  await expect(ranking.getByRole("slider", { name: "区间起点" })).toBeVisible();
  await expect(ranking.getByText("未经独立样本外验证")).toBeVisible();
  await expect(page).toHaveURL(/rankingStock=/);
  await expect(page.getByRole("button", { name: /提交|撤单|买入|卖出/ })).toHaveCount(0);
  expect(lifecycleRequests).toBe(1);
  await page.locator(".lifecycle-layout").screenshot({
    path: "var/evidence/wp-0040-industry-lifecycle.png",
  });
  await ranking.screenshot({
    path: "var/evidence/wp-0042-industry-research-ranking.png",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".lifecycle-heading h1")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.locator(".rotation-topbar nav").evaluate((element) => {
    (element as HTMLElement).style.display = "none";
  });
  await page.locator(".lifecycle-layout").screenshot({
    path: "var/evidence/wp-0040-industry-lifecycle-mobile.png",
  });
  await ranking.screenshot({
    path: "var/evidence/wp-0042-industry-research-ranking-mobile.png",
  });
});

test("formal industry rotation replays locally without business refetch", async ({ page }) => {
  test.setTimeout(60_000);
  let rotationRequests = 0;
  let hierarchyRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/market/industry-rotation")) rotationRequests += 1;
    if (request.url().includes("/api/market/industry-hierarchy")) hierarchyRequests += 1;
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/market?tab=industries&view=rotation&trail=20");
  await expect(page.getByText("研究观察，不是买卖信号").first()).toBeVisible();
  await expect(page.getByRole("region", { name: "行业相对轮动四象限" })).toBeVisible();
  await page.getByRole("button", { name: "上一日" }).click();
  const logicalDate = await page.getByRole("time").textContent();
  const firstNode = page.locator(".rotation-node").first();
  const startStyle = await firstNode.getAttribute("style");
  await page.getByRole("button", { name: "播放" }).click();
  await page.waitForTimeout(180);
  expect(await firstNode.getAttribute("style")).not.toBe(startStyle);
  await expect(page.getByRole("time")).toHaveText(logicalDate ?? "");
  await page.getByRole("button", { name: "暂停" }).click();
  await page.getByRole("combobox", { name: "尾迹长度" }).selectOption("10");
  const expandIndustries = page.getByRole("button", { name: "展开行业列表" });
  const industryCount = Number.parseInt(
    (await expandIndustries.textContent()) ?? "0",
    10,
  );
  await expandIndustries.click();
  await expect(page.getByRole("listbox", { name: "申万一级行业" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "全部行业" }).click();
  const plot = page.getByRole("region", { name: "行业相对轮动四象限" });
  await expect(plot).toHaveAttribute("data-trail-count", String(industryCount));
  await expect(plot).toHaveAttribute("data-label-count", String(industryCount));
  expect(await labelOverlapCount(plot.locator(".rotation-node span"))).toBe(0);
  mkdirSync("var/evidence", { recursive: true });
  await page.screenshot({
    path: "var/evidence/wp-0037-industry-persistent-labels.png",
    fullPage: true,
  });
  const secondNode = page.locator(".rotation-node").nth(1);
  const secondIndustry = (await secondNode.locator("span").textContent())
    ?.split(" · ")[0];
  await secondNode.click();
  await expect(page.getByRole("heading", {
    name: secondIndustry ?? "",
  })).toBeVisible();
  const selectedLabel = secondNode.locator("span");
  expect((await selectedLabel.boundingBox())?.height).toBeGreaterThanOrEqual(28);
  expect(await selectedLabel.evaluate((element) =>
    element.scrollHeight > element.clientHeight
    || element.scrollWidth > element.clientWidth)).toBe(false);
  expect(await selectedLabel.locator("b").evaluate((element) =>
    element.scrollWidth > element.clientWidth)).toBe(false);
  await page.screenshot({ path: "var/evidence/wp-0037-selected-label-readable.png", fullPage: true });
  const secondClass = await secondNode.getAttribute("class") ?? "";
  const secondQuadrant = ["leading", "weakening", "lagging", "improving"]
    .find((value) => secondClass.includes(`rotation-node--${value}`));
  expect(secondQuadrant).toBeTruthy();
  await page.getByRole("combobox", { name: "象限筛选" })
    .selectOption(secondQuadrant ?? "");
  await page.getByRole("combobox", { name: "排序字段" }).selectOption("speed");
  await page.getByRole("combobox", { name: "排序方向" }).selectOption("desc");
  await expect(page).toHaveURL(/quadrant=/);
  await expect(page).toHaveURL(/sort=speed/);
  await expect(page.locator(".rotation-node.is-dimmed")).not.toHaveCount(0);
  expect(rotationRequests).toBe(1);
  const endpointGap = await page.evaluate(() => {
    const path = document.querySelector<SVGPathElement>(".rotation-trail path.is-selected");
    const node = document.querySelector<HTMLElement>(".rotation-node.is-selected");
    const svg = document.querySelector<SVGSVGElement>(".rotation-trail");
    if (!path || !node || !svg) return Number.POSITIVE_INFINITY;
    const values = path.getAttribute("d")?.match(/-?\d+(?:\.\d+)?/g)?.map(Number) ?? [];
    const svgBox = svg.getBoundingClientRect();
    const nodeBox = node.getBoundingClientRect();
    const x = svgBox.left + (values.at(-2) ?? 0) / 100 * svgBox.width;
    const y = svgBox.top + (values.at(-1) ?? 0) / 100 * svgBox.height;
    return Math.hypot(x - (nodeBox.left + nodeBox.width / 2),
      y - (nodeBox.top + nodeBox.height / 2));
  });
  expect(endpointGap).toBeLessThanOrEqual(2);
  await page.getByRole("button", { name: "进入二级行业" }).click();
  await expect(page.getByText("二级行业", { exact: true })).toBeVisible();
  await page.locator(".hierarchy-list button").first().click();
  const stockPlot = page.getByRole("region", { name: "个股相对轮动四象限" });
  await expect(stockPlot).toBeVisible();
  const selectedStock = stockPlot.locator(".rotation-node").nth(1);
  await page.route("**/api/market/industry-hierarchy?*instrument_id=*", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.continue();
  }, { times: 1 });
  await selectedStock.click();
  await expect(page.locator(".stock-update-status")).toContainText("正在切换至");
  await expect(stockPlot).toBeVisible();
  await expect(page.locator(".stock-update-status")).not.toBeVisible();
  const commonWorkbench = page.getByRole("link", { name: /打开通用个股工作面/ });
  await expect(commonWorkbench).toBeVisible();
  await expect(commonWorkbench).toHaveAttribute(
    "href",
    /\/stocks\/.+data_snapshot_id=snapshot%3Asha256%3A/,
  );
  expect(hierarchyRequests).toBeGreaterThanOrEqual(2);
  await page.getByRole("combobox", { name: "个股排序字段" }).selectOption("speed");
  await page.getByRole("combobox", { name: "个股排序方向" }).selectOption("desc");
  await expect(page).toHaveURL(/stock_sort=speed/);
  await expect(page.locator(".stock-navigator .rotation-ranked-list small").first())
    .toContainText(/X .*Y .*速度/);
  await page.getByRole("button", { name: "展开聚焦" }).click();
  await expect(page.getByRole("button", { name: "收起" })).toBeVisible();
  await expect(stockPlot).toHaveAttribute("data-trail-count", "1");
  const focusedPlotBox = await stockPlot.boundingBox();
  expect(focusedPlotBox?.width).toBeGreaterThanOrEqual(680);
  expect(focusedPlotBox?.height).toBeGreaterThanOrEqual(520);
  await page.getByRole("button", { name: "放大象限图" }).click();
  await expect(stockPlot).toHaveAttribute("data-zoom", "1.35");
  await page.getByRole("button", { name: "适配全部" }).click();
  await expect(page.getByText("名称 · 全部常驻")).toBeVisible();
  await expect(stockPlot).toHaveAttribute(
    "data-label-count",
    String(await stockPlot.locator(".rotation-node").count()),
  );
  expect(await labelOverlapCount(stockPlot.locator(".rotation-node span"))).toBe(0);
  await page.screenshot({
    path: "var/evidence/wp-0036-stock-rotation-focus.png",
    fullPage: true,
  });
  await page.screenshot({
    path: "var/evidence/wp-0037-stock-persistent-labels.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.screenshot({
    path: "var/evidence/wp-0036-stock-rotation-focus-mobile.png",
    fullPage: true,
  });
  expect(await labelOverlapCount(stockPlot.locator(".rotation-node span"))).toBe(0);
  await page.screenshot({
    path: "var/evidence/wp-0037-stock-persistent-labels-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("button", { name: "收起" }).click();
  await expect(page.getByRole("button", { name: "展开聚焦" })).toBeVisible();
  await page.screenshot({
    path: "var/evidence/wp-0034-motion-filter-sort-stock.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "一级行业" }).click();
  await page.getByRole("button", { name: "公式与口径" }).click();
  await expect(page.getByRole("complementary", {
    name: "公式与口径",
  })).toContainText("价格相对强弱，而非资金净流入");
  await expect(page.getByRole("complementary", {
    name: "公式与口径",
  })).toContainText("tanh");
  await page.getByRole("button", { name: "关闭公式抽屉" }).click();
  await page.getByRole("button", { name: "整段" }).click();
  await expect(page.getByRole("combobox", { name: "整段播放时长" })).toBeVisible();
  await page.getByRole("combobox", { name: "整段播放时长" }).selectOption("10");
  await secondNode.click();
  await expect(page.getByRole("heading", { name: `${industryCount} 个行业` })).toBeVisible();
  await expect(page).not.toHaveURL(/industry=/);
  expect(rotationRequests).toBe(1);

  await page.screenshot({
    path: "var/evidence/wp-0028-market-rotation.png",
    fullPage: true,
  });
  await page.screenshot({
    path: "var/evidence/wp-0034-motion-filter-sort.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByText("研究观察，不是买卖信号").first()).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.screenshot({
    path: "var/evidence/wp-0028-market-rotation-mobile.png",
    fullPage: true,
  });
  await page.screenshot({
    path: "var/evidence/wp-0034-motion-filter-sort-mobile.png",
    fullPage: true,
  });
});

async function labelOverlapCount(labels: import("@playwright/test").Locator) {
  return labels.evaluateAll((elements) => {
    const boxes = elements.map((element) => element.getBoundingClientRect());
    let overlaps = 0;
    for (let left = 0; left < boxes.length; left += 1) {
      for (let right = left + 1; right < boxes.length; right += 1) {
        if (
          boxes[left].left < boxes[right].right
          && boxes[left].right > boxes[right].left
          && boxes[left].top < boxes[right].bottom
          && boxes[left].bottom > boxes[right].top
        ) overlaps += 1;
      }
    }
    return overlaps;
  });
}
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
  await expect(page.locator(".chart-legend strong").first()).not.toHaveText("移动指针查看");

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

test("Paper operations stays blocked until the exact limit is approved", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto("/execution");
  await expect(page.getByRole("heading", { name: "一笔金丝雀，一条恢复路径" })).toBeVisible();
  await expect(page.getByText("605208.SH")).toBeVisible();
  await expect(page.getByText("等待窗口内确认")).toBeVisible();
  await expect(page.getByText("未确认时只查询恢复，不自动重提。")).toBeVisible();
  await expect(page.getByRole("button", { name: /提交|买入/ })).toHaveCount(0);

  mkdirSync("var/evidence", { recursive: true });
  await page.screenshot({
    path: "var/evidence/wp-0020-paper-operations.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "一笔金丝雀，一条恢复路径" })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
  await page.screenshot({
    path: "var/evidence/wp-0020-paper-operations-mobile.png",
    fullPage: true,
  });
});
