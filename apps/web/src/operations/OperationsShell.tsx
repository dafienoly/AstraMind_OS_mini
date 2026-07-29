import { useCallback, useEffect, useRef, useState } from "react";

import { useRouteLoadPhase } from "../app-shell/routeProgress";
import type {
  DailyOperations,
  DailyPipelineStatus,
  DailyRunRequestAction,
  OperationsPayload,
  OperationsState,
  PaperOperations,
} from "./types";
import {
  ExecutionView,
  formatTime,
  PortfolioView,
  stateLabel,
  SystemView,
  TodayView,
} from "./OperationsViews";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

type Destination = "today" | "portfolio" | "execution" | "system";

export function OperationsShell({ destination }: { destination: Destination }) {
  const [state, setState] = useState<OperationsState>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const hasProjection = useRef(false);

  const refresh = useCallback(() => {
    const controller = new AbortController();
    setState((current) => current.kind === "ready" ? current : { kind: "loading" });
    setLocalError(null);
    setRefreshing(true);
    Promise.all([
      required<PaperOperations>("/api/execution/paper-operations", controller.signal),
      optional<DailyOperations>("/api/system/daily-operations", controller.signal),
    ])
      .then(([paper, daily]) => ({ paper, daily }))
      .then((value) => {
        hasProjection.current = true;
        setState({ kind: "ready", value });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          const message = error instanceof Error ? error.message : "未知错误";
          if (hasProjection.current) {
            setLocalError(`刷新失败：${message}。仍显示上一次本地投影。`);
          } else {
            setState({ kind: "error", message });
          }
        }
      })
      .finally(() => setRefreshing(false));
    return () => controller.abort();
  }, []);

  useEffect(() => refresh(), [refresh]);
  useRouteLoadPhase(
    state.kind === "loading" ? "loading_content" : state.kind === "ready" ? "ready" : "error",
    state.kind === "loading" ? "正在读取本地运行投影" : "运行工作面加载完成",
  );

  const registerRequest = useCallback(async (action: DailyRunRequestAction) => {
    if (state.kind !== "ready" || !state.value.daily) return;
    const latest = state.value.daily.latest_run;
    setLocalError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/system/daily-run-requests`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AstraMind-Local-Action": "daily-ops-v1",
        },
        body: JSON.stringify(action === "run" ? {
          action,
          target_date: latest?.target_date
            ?? state.value.daily.pipeline?.target_date
            ?? shanghaiDate(state.value.daily.as_of),
        } : {
          action,
          run_id: latest?.run_id,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      refresh();
    } catch (error) {
      setLocalError(
        `请求登记失败：${error instanceof Error ? error.message : "未知错误"}。没有执行外部动作。`,
      );
    }
  }, [refresh, state]);

  return (
    <div className="ops-app">
      {state.kind === "ready" ? (
        <>
          <DecisionSpine value={state.value} />
          {localError && <p className="ops-local-error" role="alert">{localError}</p>}
          {destination === "today" && (
            <TodayView value={state.value} onDailyAction={registerRequest} />
          )}
          {destination === "portfolio" && <PortfolioView value={state.value.paper} />}
          {destination === "execution" && <ExecutionView value={state.value.paper} />}
          {destination === "system" && (
            <SystemView
              isRefreshing={refreshing}
              onDailyAction={registerRequest}
              onRefresh={refresh}
              value={state.value}
            />
          )}
        </>
      ) : (
        <main className="ops-main">
          <StatePanel state={state} onRefresh={refresh} />
        </main>
      )}
    </div>
  );
}

function DecisionSpine({ value }: { value: OperationsPayload }) {
  const ready = value.paper.blocker_codes.length === 0;
  const dataReady = value.daily?.pipeline?.state === "current";
  return (
    <div className="ops-strip" aria-label="决策状态带">
      <span data-state={dataReady ? "ready" : "blocked"}>
        数据 · {pipelineLabel(value.daily?.pipeline ?? null)}
      </span>
      <span data-state="ready">风险 · 50,000元上限</span>
      <span data-state={ready ? "ready" : "blocked"}>
        授权 · {stateLabel(value.paper.canary_state)}
      </span>
      <span data-state="blocked">订单 · {value.paper.intent_count} 笔意图</span>
      <time dateTime={value.paper.as_of}>{formatTime(value.paper.as_of)} 截止</time>
    </div>
  );
}

function shanghaiDate(value: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}

async function required<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

async function optional<T>(path: string, signal: AbortSignal): Promise<T | null> {
  const response = await fetch(`${apiBaseUrl}${path}`, { signal });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return (await response.json()) as T;
}

function pipelineLabel(value: DailyPipelineStatus | null) {
  if (!value) return "尚未运行";
  if (value.state === "current") return `${value.target_date} 已提交`;
  if (value.state === "waiting_provider") return `${value.target_date} 等待提供方`;
  if (value.state === "recovery_required") return "等待恢复";
  return value.state;
}

function StatePanel({ state, onRefresh }: { state: OperationsState; onRefresh: () => void }) {
  return (
    <section className="state-panel" aria-live="polite">
      <p className="eyebrow">PAPER OPERATIONS</p>
      <h1>{state.kind === "loading" ? "正在读取本地投影" : "Paper 投影不可用"}</h1>
      <p>{state.kind === "error" ? `${state.message}。没有券商动作。` : "正在核对授权、账户基线和事件账本。"}</p>
      {state.kind === "error" && <button onClick={onRefresh} type="button">重新读取</button>}
    </section>
  );
}
