import { useEffect, useMemo, useState, type ReactNode } from "react";

import { useRouteLoadPhase } from "../app-shell/routeProgress";
import { TechnicalDetails } from "../business-language/TechnicalDetails";
import {
  marketBusinessText,
  marketBusinessTexts,
} from "../business-language/marketBusinessText";
import { useRealtimeInstrumentDetail } from "../market-dashboard/realtime/useRealtimeInstruments";
import { fetchStockWorkbench } from "./client";
import { fallbackReturnHref, readStockFocusRequest } from "./focus";
import { SecurityMarketInspector } from "./SecurityMarketInspector";
import type { RealtimeInstrumentQuote } from "../market-dashboard/types";
import type { StockWorkbenchProjection } from "./types";

type Load =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; value: StockWorkbenchProjection };

export function StockWorkbenchPage() {
  const instrumentId = decodeURIComponent(window.location.pathname.split("/").at(-1) ?? "");
  const search = window.location.search;
  const request = useMemo(readStockFocusRequest, [search]);
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const live = useRealtimeInstrumentDetail(
    request.mode === "historical_replay" || request.mode === "sealed_evidence"
      ? null
      : instrumentId,
  );
  useEffect(() => {
    const controller = new AbortController();
    setLoad({ kind: "loading" });
    void fetchStockWorkbench(instrumentId, request, controller.signal)
      .then((value) => setLoad({ kind: "ready", value }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setLoad({
            kind: "error",
            message: error instanceof Error ? error.message : "个股工作面不可用",
          });
        }
      });
    return () => controller.abort();
  }, [instrumentId, request]);
  useRouteLoadPhase(
    load.kind === "loading" ? "loading_content" : load.kind === "error" ? "error" : "ready",
    load.kind === "loading" ? `正在读取 ${instrumentId} 的同快照证据`
      : load.kind === "error" ? "个股工作面加载失败" : "个股工作面已就绪",
  );
  if (load.kind !== "ready") return <StockWorkbenchState load={load} />;
  return <StockWorkbenchReady value={load.value} live={live} />;
}

function StockWorkbenchState({ load }: { load: Exclude<Load, { kind: "ready" }> }) {
  return <main className="stock-workbench-state">
    <p className="eyebrow">通用个股工作面</p>
    <h1>{load.kind === "loading" ? "正在固定证券证据" : "个股工作面不可用"}</h1>
    <p>{load.kind === "loading"
      ? "正在读取完成日行情、点时行业、估值和股东证据。"
      : load.message}</p>
  </main>;
}

function StockWorkbenchReady({
  value,
  live,
}: {
  value: StockWorkbenchProjection;
  live: ReturnType<typeof useRealtimeInstrumentDetail>;
}) {
  const quote = live.quote ?? value.realtime_market_overlay?.quote ?? null;
  const minutes = live.minutes.length
    ? live.minutes
    : value.realtime_market_overlay?.minutes ?? [];
  const state = live.quote
    ? live.state
    : value.realtime_market_overlay?.state ?? "disconnected";
  const identity = value.instrument_identity;
  const returnHref = fallbackReturnHref(
    value.focus.return_target,
    value.focus.industry_code ?? undefined,
  );
  return <main className="stock-workbench">
    <nav className="stock-breadcrumb" aria-label="个股来源">
      <a href={returnHref}>← 返回{originLabel(value.focus.origin)}</a>
      <span>›</span><strong>{identity.instrument_name}</strong>
    </nav>
    <header className="stock-market-tape">
      <div>
        <p className="eyebrow">{originLabel(value.focus.origin)} · {modeLabel(value.focus.mode)}</p>
        <h1>{identity.instrument_name} <code>{identity.instrument_id}</code></h1>
        <p>{value.industry_context.l1_name ?? "行业不可用"} / {
          value.industry_context.l2_name ?? "二级行业不可用"
        }</p>
      </div>
      <div className="stock-last" data-state={state}>
        <strong>{price(quote?.last_price)}</strong>
        <span>{signed(quote?.change_percent)}</span>
        <small>{marketBusinessText(state)}{state === "current" ? " · 1 秒" : ""}</small>
      </div>
      <DayRange quote={quote} />
    </header>
    <SecurityMarketInspector
      completed={value.completed_market_evidence}
      dataSnapshotId={value.focus.data_snapshot_id}
      evidenceCutoff={value.focus.as_of}
      instrumentId={identity.instrument_id}
      instrumentName={identity.instrument_name}
      instrumentType="stock"
      realtime={{ state, quote, minutes }}
    />
    <div className="stock-context-grid">
      <EvidencePanel title="估值与成交">
        <Metric label="PE(TTM)" value={number(value.stock_evidence.fundamental?.price_earnings_ttm)} />
        <Metric label="PB" value={number(value.stock_evidence.fundamental?.price_book)} />
        <Metric label="换手率" value={percent(value.stock_evidence.fundamental?.turnover_rate)} />
        <Metric label="总市值" value={amount(value.stock_evidence.fundamental?.total_market_value_cny)} />
      </EvidencePanel>
      <EvidencePanel title="股东户数">
        <Metric
          label="状态"
          value={marketBusinessText(value.stock_evidence.shareholder_concentration.status)}
        />
        <Metric label="户数" value={integer(value.stock_evidence.shareholder_concentration.holder_count)} />
        <Metric label="变化" value={percent(value.stock_evidence.shareholder_concentration.change_rate)} />
        <Metric label="可用时间" value={
          value.stock_evidence.shareholder_concentration.available_at?.slice(0, 10) ?? "—"
        } />
      </EvidencePanel>
      <EvidencePanel title="数据证据">
        <Metric
          label="完成日来源"
          value={marketBusinessText(value.completed_market_evidence.evidence.provider)}
        />
        <Metric
          label="实时来源"
          value={marketBusinessText(value.realtime_market_overlay?.provider)}
        />
        <Metric label="证据截止" value={value.focus.as_of} />
        <Metric label="数据版本" value={`更新至 ${value.focus.as_of}`} />
      </EvidencePanel>
    </div>
    {value.known_gaps.length ? <p className="stock-workbench-gaps">
      数据说明：{marketBusinessTexts(value.known_gaps).join(" · ")}
    </p> : null}
    <TechnicalDetails entries={[
      {
        label: "完成日提供方路由",
        value: value.completed_market_evidence.evidence.provider,
      },
      { label: "实时提供方路由", value: value.realtime_market_overlay?.provider },
      { label: "内容身份", value: value.content_identity },
      { label: "缺口代码", value: value.known_gaps },
    ]} />
    <footer>只读市场证据，不创建组合目标、委托或订单。</footer>
  </main>;
}

function DayRange({ quote }: { quote: RealtimeInstrumentQuote | null }) {
  const low = quote?.lower_limit;
  const high = quote?.upper_limit;
  const current = quote?.last_price;
  const position = low != null && high != null && current != null && high > low
    ? Math.max(0, Math.min(100, ((current - low) / (high - low)) * 100))
    : null;
  return <section className="stock-day-range" aria-label="当日行情尺">
    <div><span>跌停 {price(low)}</span><span>现价位置</span><span>涨停 {price(high)}</span></div>
    <i>{position !== null ? <b style={{ left: `${position}%` }} /> : null}</i>
    <small>低 {price(quote?.low_price)} · 昨收 {price(quote?.previous_close)} · 高 {price(quote?.high_price)}</small>
  </section>;
}

function EvidencePanel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="stock-context-panel"><h2>{title}</h2><dl>{children}</dl></section>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function originLabel(value: StockWorkbenchProjection["focus"]["origin"]) {
  const labels: Record<typeof value, string> = {
    watchlist: "个股观察",
    industry_rotation: "行业相对轮动",
    industry_lifecycle: "行业生命周期",
    industry_ranking: "行业内研究排序",
    strategy_candidate: "策略竞技场",
    portfolio_holding: "组合持仓",
    attention_case: "需要你处理",
  };
  return labels[value];
}

function modeLabel(value: StockWorkbenchProjection["focus"]["mode"]) {
  return value === "current" ? "当前会话"
    : value === "completed" ? "完成日证据"
      : value === "historical_replay" ? "历史回放" : "封存证据";
}

function price(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(3);
}
function signed(value: number | null | undefined) {
  return value == null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}
function number(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(2);
}
function percent(value: number | null | undefined) {
  return value == null ? "—" : `${value.toFixed(2)}%`;
}
function integer(value: number | null | undefined) {
  return value == null ? "—" : Math.round(value).toLocaleString("zh-CN");
}
function amount(value: number | null | undefined) {
  return value == null ? "—" : `${(value / 100_000_000).toFixed(2)} 亿元`;
}
