import { expect, test } from "vitest";

import type {
  ShareholderConcentrationEvidence,
  StockEvidence,
  StockFundamentalEvidence,
} from "./rotationTypes";
import { stockEvidenceAtDate } from "./stockEvidenceTimeline";

const fundamentals: StockFundamentalEvidence[] = [
  {
    market_date: "2026-07-18",
    available_at: "2026-07-18T18:00:00+08:00",
    latest_close: 10,
    percent_change: 1,
    turnover_rate: 2,
    price_earnings_ttm: 20,
    price_book: 2,
    total_market_value_cny: 100,
    circulating_market_value_cny: 80,
    amount_cny: 50,
  },
  {
    market_date: "2026-07-20",
    available_at: "2026-07-20T18:00:00+08:00",
    latest_close: 12,
    percent_change: 2,
    turnover_rate: 3,
    price_earnings_ttm: 22,
    price_book: 2.2,
    total_market_value_cny: 120,
    circulating_market_value_cny: 90,
    amount_cny: 60,
  },
];
const holders: ShareholderConcentrationEvidence[] = [
  holder("2026-04-18", 1000, "insufficient_history"),
  holder("2026-07-18", 900, "ready"),
];
const evidence: StockEvidence = {
  instrument_id: "000001.SZ",
  instrument_name: "合成股票",
  as_of: "2026-07-22",
  fundamental: fundamentals[1],
  fundamental_history: fundamentals,
  shareholder_concentration: holders[1],
  shareholder_concentration_history: holders,
  known_gaps: [],
};

test("selects fundamental and shareholder evidence available on the hovered date", () => {
  const selected = stockEvidenceAtDate(evidence, "2026-07-19");
  expect(selected.fundamental?.market_date).toBe("2026-07-18");
  expect(selected.shareholder.holder_count).toBe(900);
  expect(selected.shareholder.observation_age_days).toBe(1);
});

test("never backfills evidence that was not available on the hovered date", () => {
  const beforeLatestHolder = stockEvidenceAtDate(evidence, "2026-07-17");
  expect(beforeLatestHolder.fundamental).toBeNull();
  expect(beforeLatestHolder.shareholder.holder_count).toBe(1000);
  const beforeAllHolders = stockEvidenceAtDate(evidence, "2026-04-17");
  expect(beforeAllHolders.shareholder.status).toBe("unavailable");
  expect(beforeAllHolders.shareholder.known_gaps)
    .toContain("shareholder_count_not_yet_available_at_hover_date");
});

function holder(
  availableDate: string,
  holderCount: number,
  status: ShareholderConcentrationEvidence["status"],
): ShareholderConcentrationEvidence {
  return {
    status,
    announced_on: availableDate,
    reporting_period: availableDate,
    available_at: `${availableDate}T18:00:00+08:00`,
    holder_count: holderCount,
    previous_holder_count: status === "ready" ? 1000 : null,
    change_rate: status === "ready" ? -0.1 : null,
    direction: status === "ready" ? "concentrating" : null,
    consecutive_periods: status === "ready" ? 1 : 0,
    observation_age_days: 0,
    known_gaps: status === "ready" ? [] : ["shareholder_count_previous_period_unavailable"],
  };
}
