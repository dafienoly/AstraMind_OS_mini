import type {
  ShareholderConcentrationEvidence,
  StockEvidence,
  StockFundamentalEvidence,
} from "./rotationTypes";

const shanghaiDateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

export function stockEvidenceAtDate(evidence: StockEvidence, hoverDate: string) {
  const fundamentals = evidence.fundamental_history?.length
    ? evidence.fundamental_history
    : evidence.fundamental ? [evidence.fundamental] : [];
  const holders = evidence.shareholder_concentration_history?.length
    ? evidence.shareholder_concentration_history
    : [evidence.shareholder_concentration];
  return {
    fundamental: latestFundamental(fundamentals, hoverDate),
    shareholder: latestShareholder(holders, hoverDate),
  };
}

function latestFundamental(
  history: StockFundamentalEvidence[],
  hoverDate: string,
) {
  return history.reduce<StockFundamentalEvidence | null>((latest, item) => {
    if (item.market_date > hoverDate || shanghaiDate(item.available_at) > hoverDate) {
      return latest;
    }
    return !latest || item.market_date > latest.market_date ? item : latest;
  }, null);
}

function latestShareholder(
  history: ShareholderConcentrationEvidence[],
  hoverDate: string,
) {
  const latest = history.reduce<ShareholderConcentrationEvidence | null>((selected, item) => {
    if (!item.available_at || shanghaiDate(item.available_at) > hoverDate) return selected;
    if (!selected?.available_at || item.available_at > selected.available_at) return item;
    return selected;
  }, null);
  if (!latest) {
    const structuralGap = history.find((item) =>
      item.status === "unavailable" && item.available_at === null);
    return structuralGap ?? unavailableShareholder();
  }
  return {
    ...latest,
    observation_age_days: latest.announced_on
      ? calendarDays(latest.announced_on, hoverDate)
      : null,
  };
}

function shanghaiDate(value: string) {
  const parts = Object.fromEntries(
    shanghaiDateFormatter.formatToParts(new Date(value))
      .map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function calendarDays(from: string, to: string) {
  const milliseconds = Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`);
  return Math.max(0, Math.round(milliseconds / 86_400_000));
}

function unavailableShareholder(): ShareholderConcentrationEvidence {
  return {
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
    known_gaps: ["shareholder_count_not_yet_available_at_hover_date"],
  };
}
