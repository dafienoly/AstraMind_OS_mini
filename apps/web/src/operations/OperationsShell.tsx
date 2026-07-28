import { useCallback, useEffect, useState } from "react";

import type { OperationsState, PaperOperations } from "./types";
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

const nav: { id: Destination | "market"; label: string; href: string }[] = [
  { id: "today", label: "今日", href: "/today" },
  { id: "market", label: "市场", href: "/market?tab=industries&view=rotation" },
  { id: "portfolio", label: "组合", href: "/portfolio" },
  { id: "execution", label: "订单", href: "/execution" },
  { id: "system", label: "系统", href: "/system" },
];

export function OperationsShell({ destination }: { destination: Destination }) {
  const [state, setState] = useState<OperationsState>({ kind: "loading" });

  const refresh = useCallback(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    fetch(`${apiBaseUrl}/api/execution/paper-operations`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return (await response.json()) as PaperOperations;
      })
      .then((value) => setState({ kind: "ready", value }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            kind: "error",
            message: error instanceof Error ? error.message : "未知错误",
          });
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => refresh(), [refresh]);

  return (
    <div className="ops-app">
      <header className="ops-topbar">
        <a className="wordmark" href="/today">
          ASTRA<span>MIND</span>
        </a>
        <nav aria-label="一级导航">
          {nav.map((item) => (
            <a
              aria-current={item.id === destination ? "page" : undefined}
              href={item.href}
              key={item.id}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <span className="mode-pill">PAPER · SIMULATION</span>
      </header>
      {state.kind === "ready" ? (
        <>
          <DecisionSpine value={state.value} />
          {destination === "today" && <TodayView value={state.value} />}
          {destination === "portfolio" && <PortfolioView value={state.value} />}
          {destination === "execution" && <ExecutionView value={state.value} />}
          {destination === "system" && <SystemView value={state.value} onRefresh={refresh} />}
        </>
      ) : (
        <main className="ops-main">
          <StatePanel state={state} onRefresh={refresh} />
        </main>
      )}
    </div>
  );
}

function DecisionSpine({ value }: { value: PaperOperations }) {
  const ready = value.blocker_codes.length === 0;
  return (
    <div className="ops-strip" aria-label="决策状态带">
      <span data-state="ready">数据 · 目标已绑定</span>
      <span data-state="ready">风险 · 50,000元上限</span>
      <span data-state={ready ? "ready" : "blocked"}>
        授权 · {stateLabel(value.canary_state)}
      </span>
      <span data-state="blocked">订单 · {value.intent_count} 笔意图</span>
      <time dateTime={value.as_of}>{formatTime(value.as_of)} 截止</time>
    </div>
  );
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
