import { useCallback, useEffect, useMemo, useState } from "react";

import { useRouteLoadPhase } from "../../app-shell/routeProgress";
import { marketBusinessText } from "../../business-language/marketBusinessText";
import { SecurityMarketInspector } from "../../stock-workbench/SecurityMarketInspector";
import {
  fetchEtfRotation,
  MarketDashboardFetchError,
} from "../marketDashboardClient";
import type { EtfRotationProjection } from "../types";
import { EtfCandidateList } from "./EtfCandidateList";
import { EtfFunnel } from "./EtfFunnel";
import { EtfInspector } from "./EtfInspector";
import { etfCandidateStateLabel } from "./etfLabels";
import {
  useRealtimeInstrumentDetail,
  useRealtimeInstruments,
} from "../realtime/useRealtimeInstruments";
import { ModelEvidenceBand } from "../model-evidence/ModelEvidenceBand";

type LoadState =
  | { kind: "loading" }
  | { kind: "empty" | "error"; message: string }
  | { kind: "ready"; value: EtfRotationProjection };

export function EtfRotationPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState<string | null>(
    () => new URLSearchParams(window.location.search).get("etf"),
  );
  const load = useCallback(async (signal?: AbortSignal, force = false) => {
    try {
      const value = await fetchEtfRotation(signal, force);
      setState({ kind: "ready", value });
      setSelected((current) => current ?? value.selected_etf_code);
    } catch (error) {
      if (!signal?.aborted) {
        setState({
          kind: error instanceof MarketDashboardFetchError ? error.kind : "error",
          message: error instanceof Error ? error.message : "未知错误",
        });
      }
    } finally {
      if (!signal?.aborted) setRefreshing(false);
    }
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  useEffect(() => {
    const url = new URL(window.location.href);
    if (selected) url.searchParams.set("etf", selected);
    else url.searchParams.delete("etf");
    window.history.replaceState(null, "", url);
  }, [selected]);
  const candidate = useMemo(
    () => state.kind === "ready"
      ? state.value.candidates.find((item) => item.etf_code === selected) ?? null
      : null,
    [selected, state],
  );
  const detail = useRealtimeInstrumentDetail(candidate?.etf_code ?? null);
  const candidateCodes = useMemo(
    () => state.kind === "ready"
      ? state.value.candidates.flatMap((item) => item.etf_code ? [item.etf_code] : [])
      : [],
    [state],
  );
  const realtime = useRealtimeInstruments(candidateCodes);
  const liveQuotes = useMemo(
    () => new Map((realtime.projection?.quotes ?? []).map((quote) => [quote.instrument_id, quote])),
    [realtime.projection?.quotes],
  );
  useEtfRoutePhase(state);
  if (state.kind !== "ready") {
    return <EtfLoadState state={state} />;
  }
  const value = state.value;
  const latestDailyEvidence = latestEvidenceDate(value);
  const realtimeState = realtime.projection?.state ?? "disconnected";
  return <div className="rotation-app market-dashboard-app">
    <div className="etf-status" data-state={value.status}>
      <strong>{value.status === "ready"
        ? "日线研究就绪"
        : value.status === "stale"
          ? "日线证据待更新"
          : "研究门禁关闭"}</strong>
      <span>决策截止 {value.evidence_cutoff ?? "—"}</span>
      <span>ETF 日线最新 {latestDailyEvidence ?? "—"}</span>
      <span>MiniQMT 实时：{realtimeStateLabel(realtimeState)}</span>
      <span>{value.strategy_version}</span>
      <button disabled={refreshing} onClick={() => {
        setRefreshing(true);
        void load(undefined, true);
      }} type="button">{refreshing ? "刷新中…" : "刷新快照"}</button>
      <em>研究目标，不是订单</em>
    </div>
    <main className="rotation-main etf-rotation-main">
      <EtfMethodHeading dataCutoff={value.evidence_cutoff} />
      <EtfFunnel value={value.funnel} />
      <div className="etf-workspace">
        <EtfCandidateList
          candidates={value.candidates}
          liveQuotes={liveQuotes}
          onSelect={setSelected}
          selected={selected}
        />
        {candidate?.etf_code ? <SecurityMarketInspector
          completed={{
            daily: candidate.candles,
            weekly: candidate.weekly_candles,
            monthly: candidate.monthly_candles,
          }}
          dataSnapshotId={value.data_snapshot_id}
          evidenceCutoff={value.evidence_cutoff ?? value.as_of.slice(0, 10)}
          instrumentId={candidate.etf_code}
          instrumentName={candidate.etf_name ?? candidate.etf_code}
          instrumentType="etf"
          realtime={{
            state: detail.state,
            quote: detail.quote,
            minutes: detail.minutes,
          }}
        /> : <section className="etf-chart etf-chart-empty">
          <h2>价格结构核验</h2><p>当前没有可选择的 ETF 映射。</p>
        </section>}
        <EtfInspector candidate={candidate} projection={value} />
      </div>
      <footer className="etf-replay-strip">
        <div><small>行业研究事实</small><strong>{candidate?.industry_name ?? "—"} · {candidate?.lifecycle_stage ?? "—"}</strong></div>
        <i>→</i>
        <div><small>ETF 判断</small><strong>{candidate?.etf_code ?? "—"} · {candidate
          ? etfCandidateStateLabel(candidate.state)
          : "不可用"}</strong></div>
        <i>→</i>
        <div><small>研究目标</small><strong>{value.target_draft.weights.length} 只 · 现金 {(value.target_draft.cash_weight * 100).toFixed(0)}%</strong></div>
        <div className="etf-replay-note"><small>回放</small><strong>{value.replay.evidence_label}</strong></div>
      </footer>
    </main>
  </div>;
}

function EtfMethodHeading({ dataCutoff }: { dataCutoff: string | null }) {
  return <>
    <header className="etf-page-heading">
      <div>
        <p className="eyebrow">市场 / ETF 轮动</p>
        <h1>方向到 ETF，再核验价格结构</h1>
        <p>价差与跟踪均为清楚标注的研究代理；当前映射和行情不足时保持现金。</p>
      </div>
      <span>周度主评估 · 日度风险检查</span>
    </header>
    <ModelEvidenceBand
      dataCutoff={dataCutoff}
      family="etf_rotation"
      horizons={["未来 20 日"]}
    />
  </>;
}

function EtfLoadState({ state }: { state: Exclude<LoadState, { kind: "ready" }> }) {
  return <div className="rotation-app market-dashboard-app">
    <main className="rotation-state">
      <p className="eyebrow">市场 / ETF 轮动</p>
      <h1>{state.kind === "loading" ? "正在形成 ETF 研究漏斗" : "ETF 研究不可用"}</h1>
      <p>{state.kind === "loading"
        ? "固定一个不可变快照后计算代理门禁。"
        : state.message}</p>
    </main>
  </div>;
}

function latestEvidenceDate(value: EtfRotationProjection) {
  const dates = value.candidates.flatMap((candidate) =>
    candidate.candles.map((candle) => candle.trade_date)
  );
  return dates.length ? dates.sort().at(-1) ?? null : null;
}

function realtimeStateLabel(state: string) {
  return marketBusinessText(state);
}

function useEtfRoutePhase(state: LoadState) {
  useRouteLoadPhase(
    state.kind === "loading" ? "loading_content" : state.kind === "ready" ? "ready" : "error",
    state.kind === "loading" ? "正在形成 ETF 研究漏斗" : "ETF 轮动加载完成",
  );
}
