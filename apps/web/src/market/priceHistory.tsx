import { useEffect, useState } from "react";

import type { PriceCandle } from "../market-dashboard/types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

export type PriceHistoryWindow = "one_year" | "five_years" | "listed_since";
export type PriceInstrumentType = "stock" | "index" | "etf";

export type PriceHistoryPage = {
  instrument_type: PriceInstrumentType;
  instrument_id: string;
  instrument_name: string;
  data_snapshot_id: string;
  dataset_name: string;
  dataset_version: string;
  dataset_content_hash: string;
  evidence_cutoff: string;
  window: PriceHistoryWindow;
  requested_start: string;
  requested_end: string;
  coverage_start: string | null;
  coverage_end: string | null;
  coverage_basis:
    | "listing_date_or_earliest_reliable_record"
    | "official_launch_or_earliest_reliable_record";
  listing_date: string | null;
  schema_version: string;
  bars: PriceCandle[];
  page_size: number;
  has_more: boolean;
  next_cursor: string | null;
  known_gaps: string[];
};

type HistoryState =
  | { kind: "idle"; bars: PriceCandle[] }
  | { kind: "loading"; bars: PriceCandle[] }
  | { kind: "ready"; bars: PriceCandle[]; page: PriceHistoryPage }
  | { kind: "error"; bars: PriceCandle[]; message: string };

type StoredHistoryState = HistoryState & { requestKey: string };

export function usePriceHistory({
  instrumentType,
  instrumentId,
  dataSnapshotId,
  evidenceCutoff,
  window,
  fallback,
}: {
  instrumentType: PriceInstrumentType;
  instrumentId: string;
  dataSnapshotId: string;
  evidenceCutoff: string;
  window: PriceHistoryWindow;
  fallback: PriceCandle[];
}): HistoryState {
  const requestKey = [
    instrumentType,
    instrumentId,
    dataSnapshotId,
    evidenceCutoff,
    window,
  ].join("|");
  const [state, setState] = useState<StoredHistoryState>({
    kind: "idle",
    bars: fallback,
    requestKey,
  });
  useEffect(() => {
    if (window === "one_year") return;
    const controller = new AbortController();
    setState({ kind: "loading", bars: fallback, requestKey });
    void fetchCompleteHistory({
      instrumentType,
      instrumentId,
      dataSnapshotId,
      evidenceCutoff,
      window,
      signal: controller.signal,
    }).then(({ bars, page }) => {
      if (!controller.signal.aborted) {
        setState({ kind: "ready", bars, page, requestKey });
      }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState({
        kind: "error",
        bars: fallback,
        message: error instanceof Error ? error.message : "完整历史加载失败",
        requestKey,
      });
    });
    return () => controller.abort();
  }, [
    dataSnapshotId,
    evidenceCutoff,
    fallback,
    instrumentId,
    instrumentType,
    requestKey,
    window,
  ]);
  if (window === "one_year") return { kind: "idle", bars: fallback };
  if (state.requestKey === requestKey) return state;
  return { kind: "loading", bars: fallback };
}

export function HistoryWindowSelector({
  value,
  onChange,
  state,
}: {
  value: PriceHistoryWindow;
  onChange: (value: PriceHistoryWindow) => void;
  state?: HistoryState["kind"];
}) {
  const choices: [PriceHistoryWindow, string][] = [
    ["one_year", "近一年"],
    ["five_years", "近五年"],
    ["listed_since", "上市以来"],
  ];
  return <div className="timeframe history-window-selector" aria-label="历史范围">
    {choices.map(([key, label]) => <button
      aria-pressed={value === key}
      disabled={state === "loading" && value === key}
      className={value === key ? "active" : ""}
      key={key}
      onClick={() => onChange(key)}
      type="button"
    >{state === "loading" && value === key ? "加载中…" : label}</button>)}
  </div>;
}

async function fetchCompleteHistory({
  instrumentType,
  instrumentId,
  dataSnapshotId,
  evidenceCutoff,
  window,
  signal,
}: {
  instrumentType: PriceInstrumentType;
  instrumentId: string;
  dataSnapshotId: string;
  evidenceCutoff: string;
  window: PriceHistoryWindow;
  signal: AbortSignal;
}) {
  let cursor: string | null = null;
  let first: PriceHistoryPage | null = null;
  const bars: PriceCandle[] = [];
  const dates = new Set<string>();
  const cursors = new Set<string>();
  do {
    const query = new URLSearchParams({
      window,
      data_snapshot_id: dataSnapshotId,
      evidence_cutoff: evidenceCutoff,
      page_size: "1000",
    });
    if (cursor) query.set("cursor", cursor);
    const response = await fetch(
      `${apiBaseUrl}/api/market/history/${instrumentType}/${
        encodeURIComponent(instrumentId)
      }?${query}`,
      { signal },
    );
    if (!response.ok) throw new Error(`历史行情 HTTP ${response.status}`);
    const page = (await response.json()) as PriceHistoryPage;
    if (
      page.instrument_type !== instrumentType
      || page.instrument_id !== instrumentId
      || page.data_snapshot_id !== dataSnapshotId
      || page.evidence_cutoff !== evidenceCutoff
      || page.window !== window
    ) throw new Error("历史行情身份在分页过程中发生变化");
    if (first === null) {
      first = page;
    } else if (
      page.dataset_name !== first.dataset_name
      || page.dataset_version !== first.dataset_version
      || page.dataset_content_hash !== first.dataset_content_hash
      || page.requested_start !== first.requested_start
      || page.requested_end !== first.requested_end
    ) {
      throw new Error("历史行情数据集身份在分页过程中发生变化");
    }
    for (const bar of page.bars) {
      if (dates.has(bar.trade_date)) throw new Error("历史行情分页返回重复交易日");
      dates.add(bar.trade_date);
    }
    bars.unshift(...page.bars);
    cursor = page.has_more ? page.next_cursor : null;
    if (page.has_more && !cursor) throw new Error("历史行情分页游标缺失");
    if (cursor && cursors.has(cursor)) throw new Error("历史行情分页游标没有前进");
    if (cursor) cursors.add(cursor);
  } while (cursor);
  if (!first) throw new Error("历史行情没有返回页面");
  return { bars, page: first };
}
