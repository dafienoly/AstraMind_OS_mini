import { useEffect, useMemo, useState } from "react";

import { useRouteLoadPhase } from "../../app-shell/routeProgress";
import { stockWorkbenchHref } from "../../stock-workbench/focus";
import {
  fetchMarketWatchlist,
  fetchRealtimeInstruments,
  saveMarketWatchlist,
} from "../marketDashboardClient";
import type { RealtimeInstrumentQuote } from "../types";
import { StockSearchCombobox } from "./StockSearchCombobox";
import { useRealtimeInstruments } from "./useRealtimeInstruments";

export function StockRealtimePage() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [industryCode, setIndustryCode] = useState(
    () => new URLSearchParams(window.location.search).get("industry") ?? "",
  );
  const [source, setSource] = useState<"watchlist" | "industry">("watchlist");
  const [industryQuotes, setIndustryQuotes] = useState<RealtimeInstrumentQuote[]>([]);
  const { projection, message } = useRealtimeInstruments(watchlist);
  const quotes = source === "watchlist" ? projection?.quotes ?? [] : industryQuotes;
  const [selected, setSelected] = useState<string | null>(null);
  const [watchlistLoaded, setWatchlistLoaded] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void fetchMarketWatchlist(controller.signal)
      .then(setWatchlist)
      .finally(() => {
        if (!controller.signal.aborted) setWatchlistLoaded(true);
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (source !== "industry" || !industryCode) return;
    const controller = new AbortController();
    void fetchRealtimeInstruments([], industryCode, "stock", controller.signal)
      .then((value) => setIndustryQuotes(value.quotes));
    return () => controller.abort();
  }, [industryCode, source]);
  useEffect(() => {
    if (!selected && quotes.length) setSelected(quotes[0].instrument_id);
  }, [quotes, selected]);
  const sorted = useMemo(
    () => [...quotes].sort((left, right) => (
      (right.change_percent ?? -Infinity) - (left.change_percent ?? -Infinity)
    )),
    [quotes],
  );
  async function persist(next: string[]) {
    setWatchlist(await saveMarketWatchlist(next));
  }
  useRouteLoadPhase(
    watchlistLoaded ? "ready" : "loading_content",
    watchlistLoaded ? "个股观察已就绪" : "正在读取本地自选",
  );
  return <div className="rotation-app market-dashboard-app">
    <main className="rotation-main realtime-stock-main">
      <header className="realtime-stock-heading">
        <div><p className="eyebrow">市场 / 个股观察</p><h1>实时列表、分钟成交与五档盘口</h1>
          <p>本地自选只用于观察；状态、盘口和分钟线共享同一 MiniQMT 会话。</p></div>
        <span>只读 · 不创建目标或订单</span>
      </header>
      <div className="realtime-stock-toolbar">
        <div role="group" aria-label="证券来源">
          <button aria-pressed={source === "watchlist"} onClick={() => setSource("watchlist")}
            type="button">自选</button>
          <button aria-pressed={source === "industry"} onClick={() => setSource("industry")}
            type="button">行业成分</button>
        </div>
        {source === "watchlist" ? <StockSearchCombobox
          onAdd={(code) => void persist([...watchlist, code])}
          watchlist={watchlist}
        /> : <label>行业代码
          <input onChange={(event) => setIndustryCode(event.target.value.trim())}
            placeholder="例如 801080.SI" value={industryCode} />
        </label>}
        <span data-state={projection?.state ?? "disconnected"}>
          {message ?? (projection ? `${projection.state} · ${projection.quotes.length} 只` : "等待行情")}
        </span>
      </div>
      <div className="realtime-stock-workspace">
        <section className="realtime-quote-list" aria-label="个股实时列表">
          <header><strong>{source === "watchlist" ? "本地自选" : industryCode || "行业成分"}</strong>
            <span>{sorted.length} 只</span></header>
          {sorted.length ? sorted.map((quote) => <a
            aria-current={selected === quote.instrument_id ? "true" : undefined}
            href={stockWorkbenchHref(quote.instrument_id, {
              origin: "watchlist",
              mode: "current",
              returnTarget: "market_stocks",
              industryCode: source === "industry" ? industryCode : undefined,
            })}
            key={quote.instrument_id}
            onClick={() => setSelected(quote.instrument_id)}>
            <span><strong>{quote.instrument_name ?? quote.instrument_id}</strong>
              <code>{quote.instrument_id}</code></span>
            <span><b>{quote.last_price?.toFixed(3) ?? "—"}</b>
              <em data-sign={(quote.change_percent ?? 0) >= 0 ? "up" : "down"}>
                {signed(quote.change_percent)}
              </em></span>
            {source === "watchlist" ? <i onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              void persist(watchlist.filter((code) => code !== quote.instrument_id));
            }} role="button" tabIndex={0}>移除</i> : null}
          </a>) : <p className="realtime-list-empty">
            {source === "watchlist" ? "自选清单为空，加入证券后开始观察。" : "输入行业代码加载当前成分。"}
          </p>}
        </section>
        <aside className="realtime-selection-guide">
          <p className="eyebrow">统一查看</p>
          <h2>{selected ?? "选择一只证券"}</h2>
          <p>点击左侧证券进入通用个股工作面；分钟成交、五档盘口、日周月 K 和点时证据只维护一套。</p>
        </aside>
      </div>
    </main>
  </div>;
}

function signed(value: number | null) {
  if (value === null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}
