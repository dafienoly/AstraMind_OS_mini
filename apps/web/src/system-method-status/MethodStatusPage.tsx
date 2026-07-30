import { useState } from "react";

import { useRouteLoadPhase } from "../app-shell/routeProgress";
import type { MarketModelFamily } from "../market-dashboard/model-evidence/types";
import { MethodModelIndex, uniqueItem } from "./MethodModelIndex";
import { catalogEntry } from "./methodCatalog";
import { currentMethod, statusCopy, statusTone } from "./methodStatusPresentation";
import { MethodStatusDetail } from "./MethodStatusDetail";
import { useMethodStatusProjection } from "./useMethodStatusProjection";

export function MethodStatusPage() {
  const [selected, setSelected] = useState<MarketModelFamily>("industry_heat");
  const { state, refresh } = useMethodStatusProjection();
  const projection = state.kind === "ready" ? state.projection : null;
  const items = projection?.models ?? [];
  const item = uniqueItem(items, selected);
  const catalog = catalogEntry(selected);

  useRouteLoadPhase(
    state.kind === "loading" ? "loading_content" : state.kind === "ready" ? "ready" : "error",
    state.kind === "loading" ? "正在读取五类模型状态" : "方法与状态工作面已就绪",
  );

  return <main
    className="method-status-page"
    data-load-state={state.kind}
    data-model-state={item?.state ?? "unknown"}
  >
    <header className="method-status-heading">
      <div>
        <p className="eyebrow">SYSTEM / METHOD STATUS</p>
        <h1>当前为什么使用这个方法？</h1>
        <p>先选模型，再沿谱系尺定位下一道未通过的门。这里解释方法，不执行训练、激活或交易。</p>
      </div>
      {state.kind === "ready" ? <button
        className="method-refresh"
        disabled={state.refreshing}
        onClick={refresh}
        type="button"
      >{state.refreshing ? "正在刷新…" : "刷新状态投影"}</button> : null}
    </header>

    {state.kind === "ready" && state.refreshWarning
      ? <p className="method-refresh-warning" role="status">{state.refreshWarning}</p>
      : null}

    <section
      className="method-mobile-summary"
      data-tone={statusTone(item)}
      aria-label="当前模型摘要"
    >
      <span>{catalog.label} · {currentMethod(item)}</span>
      <strong>{state.kind === "loading" ? "状态读取中" : statusCopy(item)}</strong>
    </section>

    <div className="method-status-workspace">
      <MethodModelIndex
        items={items}
        loading={state.kind === "loading"}
        onSelect={setSelected}
        projectionTime={projection?.as_of ?? null}
        selected={selected}
      />
      <MethodStatusDetail
        catalog={catalog}
        item={item}
        onRetry={refresh}
        projection={projection}
        state={state}
      />
    </div>

    <footer className="method-readonly-boundary">
      <strong>只读边界</strong>
      <span>模型激活不等于策略晋级、组合授权或券商授权；本页没有训练、激活或交易动作。</span>
    </footer>
  </main>;
}
