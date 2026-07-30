import { expect, test } from "@playwright/test";

test("stock watchlist renders dynamic feed state through business language", async ({ page }) => {
  test.setTimeout(120_000);
  await page.addInitScript(() => {
    class NoopEventSource {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSED = 2;
      readonly CONNECTING = 0;
      readonly OPEN = 1;
      readonly CLOSED = 2;
      readonly readyState = 1;
      readonly withCredentials = false;
      onerror = null;
      onmessage = null;
      onopen = null;

      constructor(readonly url: string | URL) {}
      addEventListener() {}
      close() {}
      dispatchEvent() { return true; }
      removeEventListener() {}
    }
    window.EventSource = NoopEventSource as unknown as typeof EventSource;
  });
  await page.addInitScript((projection) => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = typeof input === "string"
        ? input
        : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/api/market/watchlist")) {
        return new Response(JSON.stringify({ instrument_ids: ["000001.SZ"] }), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        });
      }
      if (url.includes("/api/market/realtime/instruments?")) {
        return new Response(JSON.stringify(projection), {
          headers: { "Content-Type": "application/json" },
          status: 200,
        });
      }
      return originalFetch(input, init);
    };
  }, realtimeProjection());

  await page.goto("/market?tab=stocks");

  const status = page.getByLabel("实时行情状态：正在更新 · 1 只");
  await expect(status).toBeVisible();
  await expect(status).toHaveText("正在更新 · 1 只");
  await expect(page.getByText("current · 1 只", { exact: true })).toHaveCount(0);
  await expect(page.getByText("miniqmt", { exact: true })).toHaveCount(0);
  await expect(page.getByText(`sha256:${"a".repeat(64)}`, { exact: true })).toHaveCount(0);
  await expect(page.getByText("brand_new_internal_code", { exact: true })).toHaveCount(0);
});

test("approved stock inspector exposes deterministic minute scales and five-day window", async ({
  page,
}) => {
  const realtime = realtimeProjection();
  realtime.open_minutes = [minuteBar("2026-07-30T09:34:00+08:00", false)];
  const closed = [0, 1, 2, 3].map((offset) => (
    minuteBar(`2026-07-30T09:3${offset}:00+08:00`, true)
  ));
  await page.addInitScript(({ projection, realtime, closed }) => {
    class NoopEventSource {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSED = 2;
      static listener: ((event: MessageEvent<string>) => void) | null = null;
      readonly readyState = 1;
      constructor(readonly url: string | URL) {}
      addEventListener(_type: string, listener: EventListenerOrEventListenerObject) {
        NoopEventSource.listener = listener as (event: MessageEvent<string>) => void;
      }
      close() {}
      dispatchEvent() { return true; }
      removeEventListener() {}
    }
    window.EventSource = NoopEventSource as unknown as typeof EventSource;
    const state = window as unknown as {
      __barFetchCount: number;
      __emitRealtime: (value: unknown) => void;
    };
    state.__barFetchCount = 0;
    state.__emitRealtime = (value) => NoopEventSource.listener?.(
      new MessageEvent("instruments", { data: JSON.stringify(value) }),
    );
    window.fetch = async (input) => {
      const url = typeof input === "string"
        ? input
        : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/market/stocks/")) {
        return Response.json(projection);
      }
      if (url.includes("/api/market/realtime/instruments?")) {
        return Response.json(realtime);
      }
      if (url.includes("/bars?")) {
        state.__barFetchCount += 1;
        const frequency = new URL(url).searchParams.get("frequency");
        return Response.json({
          instrument_id: "000001.SZ",
          frequency_minutes: Number(frequency),
          start_date: "2026-07-30",
          end_date: "2026-07-30",
          sessions: ["2026-07-30"],
          bars: frequency === "1" ? closed : [],
          indicators: closed.map((row) => ({
            minute: row.minute,
            ma5: 10, ma10: 10, ma30: 10, ma60: 10,
            macd: 0.2, signal: 0.1, histogram: 0.2,
          })),
          indicator_state: "ready",
          known_gaps: [],
          next_cursor: `sha256:${"d".repeat(64)}`,
        });
      }
      return new Response(null, { status: 404 });
    };
  }, { projection: stockWorkbenchProjection(), realtime, closed });

  await page.goto(
    "/stocks/000001.SZ?origin=watchlist&mode=completed&return_target=market_stocks",
  );
  await expect(page.locator(".route-loading-overlay")).toHaveCount(0);
  await expect(page.getByText(/形成中 · 1 分钟/)).toBeVisible();

  await expect(page.getByLabel("分钟周期与窗口")).toBeVisible();
  for (const label of ["1 分钟", "5 分钟", "15 分钟", "30 分钟", "60 分钟", "120 分钟"]) {
    await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  await expect(page.getByRole("button", { name: "5 日", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "年 K", exact: true })).toBeVisible();
  const chart = page.getByRole("img", { name: /分钟 K 线/ });
  const box = await chart.boundingBox();
  if (!box) throw new Error("minute chart has no visible bounds");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.getByText(/DIF .* DEA .* MACD/)).toBeVisible();
  await page.getByRole("button", { name: "5 分钟", exact: true }).click();
  await expect(page.getByText(/形成中 · 5 分钟/)).toBeVisible();
  const requests = await page.evaluate(() => (
    window as unknown as { __barFetchCount: number }
  ).__barFetchCount);
  const updated = structuredClone(realtime);
  updated.open_minutes = [{
    ...minuteBar("2026-07-30T09:34:00+08:00", false),
    close: 10.8,
  }];
  await page.evaluate((value) => (
    window as unknown as { __emitRealtime: (next: unknown) => void }
  ).__emitRealtime(value), updated);
  await expect(page.getByText(/C 10.8/)).toBeVisible();
  expect(await page.evaluate(() => (
    window as unknown as { __barFetchCount: number }
  ).__barFetchCount)).toBe(requests);
  updated.open_minutes = [{
    ...updated.open_minutes[0],
    known_gaps: ["cumulative_counter_reset"],
  }];
  await page.evaluate((value) => (
    window as unknown as { __emitRealtime: (next: unknown) => void }
  ).__emitRealtime(value), updated);
  await expect(page.getByText(/形成中 · 5 分钟/)).toHaveCount(0);
  await expect(page.getByRole("img", { name: /分钟 K 线/ })).toHaveCount(0);
});

function minuteBar(minute: string, complete: boolean) {
  return {
    provider: "miniqmt",
    session_id: `sha256:${"b".repeat(64)}`,
    instrument_id: "000001.SZ",
    minute,
    open: 10,
    high: 11,
    low: 9,
    close: 10.5,
    volume: 1,
    amount: 10,
    observation_count: 1,
    source_kind: "l1",
    source_identity: `sha256:${"e".repeat(64)}`,
    is_complete: complete,
    known_gaps: [] as string[],
    lifecycle: complete ? "sealed" : "forming",
  };
}

function realtimeProjection() {
  return {
    projection_id: `sha256:${"a".repeat(64)}`,
    provider: "miniqmt",
    session_id: `sha256:${"b".repeat(64)}`,
    state: "current",
    as_of: "2026-07-30T10:00:00+08:00",
    market_date: "2026-07-30",
    quotes: [{
      instrument_id: "000001.SZ",
      instrument_name: "平安银行",
      instrument_type: "stock",
      industry_code: "801780.SI",
      market_time_ms: 1,
      received_at: "2026-07-30T10:00:00+08:00",
      last_price: 11.28,
      previous_close: 11.20,
      change_percent: 0.71,
      open_price: 11.21,
      high_price: 11.30,
      low_price: 11.18,
      volume: 1_000,
      amount: 11_280,
      upper_limit: 12.32,
      lower_limit: 10.08,
      stock_status: 0,
      status_label: "正常交易",
      bids: [],
      asks: [],
    }],
    open_minutes: [] as ReturnType<typeof minuteBar>[],
    known_gaps: ["brand_new_internal_code"],
  };
}

function stockWorkbenchProjection() {
  const identity = `sha256:${"c".repeat(64)}`;
  return {
    focus: {
      focus_id: identity,
      instrument_id: "000001.SZ",
      origin: "watchlist",
      as_of: "2026-07-30",
      data_snapshot_id: `snapshot:${identity}`,
      industry_code: "801780.SI",
      mode: "completed",
      return_target: "market_stocks",
      created_at: "2026-07-30T16:00:00+08:00",
    },
    instrument_identity: {
      instrument_id: "000001.SZ",
      instrument_name: "平安银行",
      exchange: "SZ",
      market: "主板",
      risk_status: null,
      is_special_treatment: false,
    },
    completed_market_evidence: {
      evidence: {
        state: "ready",
        as_of: "2026-07-30",
        provider: "tushare",
        content_identity: identity,
        known_gaps: [],
      },
      daily: [],
      weekly: [],
      monthly: [],
    },
    realtime_market_overlay: null,
    industry_context: {
      evidence: {
        state: "ready",
        as_of: "2026-07-30",
        provider: "tushare",
        content_identity: identity,
        known_gaps: [],
      },
      taxonomy: "SW",
      taxonomy_version: "SW2021",
      l1_code: "801780.SI",
      l1_name: "银行",
      l2_code: null,
      l2_name: null,
    },
    stock_evidence: {
      instrument_id: "000001.SZ",
      instrument_name: "平安银行",
      as_of: "2026-07-30",
      fundamental: null,
      shareholder_concentration: {
        status: "unavailable",
        announced_on: null,
        reporting_period: null,
        available_at: null,
        holder_count: null,
        previous_holder_count: null,
        change_rate: null,
        direction: null,
        consecutive_periods: 0,
        observation_age_days: null,
        known_gaps: [],
      },
      known_gaps: [],
    },
    content_identity: identity,
    known_gaps: [],
  };
}
