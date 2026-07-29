import { useCallback, useEffect, useState } from "react";

import { useRouteLoadPhase } from "../app-shell/routeProgress";
import { IndustryHeatView } from "./IndustryHeatView";
import { IndustryLifecycleView } from "./IndustryLifecycleView";
import { MarketStatusStrip } from "./MarketChrome";
import { RealtimePulse } from "./RealtimePulse";
import {
  fetchMarketDashboard,
  MarketDashboardFetchError,
} from "./marketDashboardClient";
import { DashboardBlocked, OverviewView } from "./OverviewView";
import type { MarketDashboardProjection } from "./types";
import { useRealtimeMarket } from "./useRealtimeMarket";
import { ModelEvidenceBand } from "./model-evidence/ModelEvidenceBand";

type LoadState =
  | { kind: "loading" }
  | { kind: "empty"; message: string }
  | { kind: "error"; message: string }
  | { kind: "ready"; projection: MarketDashboardProjection };

export function MarketDashboard({
  view,
}: {
  view: "overview" | "heatmap" | "lifecycle" | "etf";
}) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const realtime = useRealtimeMarket();
  const load = useCallback(async (signal?: AbortSignal, force = false) => {
    try {
      const projection = await fetchMarketDashboard(signal, force);
      setState({ kind: "ready", projection });
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
  useRouteLoadPhase(
    state.kind === "loading" ? "loading_content"
      : state.kind === "ready" ? "ready" : "error",
    state.kind === "loading" ? "正在读取正式市场快照" : "市场工作面加载完成",
  );

  if (state.kind !== "ready") {
    return <div className="rotation-app market-dashboard-app">
      <main className="rotation-state">
        <p className="eyebrow">市场 / {
          view === "heatmap" ? "行业热力" : view === "lifecycle" ? "生命周期结构" : "大盘"
        }</p>
        <h1>
          {state.kind === "loading"
            ? "正在读取正式市场快照"
            : state.kind === "empty"
              ? "尚无可展示的市场快照"
              : "市场服务不可用"}
        </h1>
        <p>
          {state.kind === "loading"
            ? "固定一个不可变快照后形成页面投影。"
            : state.message}
        </p>
        <strong>市场观察，不是买卖信号</strong>
      </main>
    </div>;
  }
  const projection = state.projection;
  return <div className="rotation-app market-dashboard-app">
    <MarketStatusStrip
      projection={projection}
      refreshing={refreshing}
      onRefresh={() => {
        setRefreshing(true);
        void load(undefined, true);
      }}
    />
    <main className="rotation-main market-dashboard-main">
      <RealtimePulse view={realtime} />
      {view === "heatmap" ? <ModelEvidenceBand
        dataCutoff={projection.evidence_cutoff}
        family="industry_heat"
        horizons={["未来 1 日", "未来 5 日"]}
      /> : view === "lifecycle" ? <ModelEvidenceBand
        dataCutoff={projection.evidence_cutoff}
        family="industry_lifecycle"
        horizons={["未来 20 日阶段"]}
      /> : null}
      {projection.status === "blocked" ? <DashboardBlocked gaps={projection.known_gaps} />
        : view === "overview" ? <OverviewView projection={projection} realtime={realtime} />
          : view === "heatmap" ? <IndustryHeatView projection={projection} realtime={realtime} />
            : view === "lifecycle"
              ? <IndustryLifecycleView dashboardSnapshotId={projection.data_snapshot_id}
                  realtime={realtime} />
            : null}
    </main>
  </div>;
}
