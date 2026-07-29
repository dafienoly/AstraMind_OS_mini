import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { TechnicalDetails } from "../business-language/TechnicalDetails";
import { HierarchyRotationWorkbench } from "./HierarchyRotationWorkbench";
import { StockHierarchyWorkbench } from "./StockHierarchyWorkbench";
import {
  canRetainStockWorkbench,
  clearHierarchyRequests,
  hierarchyUrl,
  loadHierarchy,
  replaceHierarchyUrl,
  retainNavigationEvidence,
} from "./hierarchyClient";
import { describeHierarchyBlock } from "./hierarchyBlockReason";
import type {
  IndustryHierarchyView,
  RotationSnapshot,
} from "./rotationTypes";

type Load =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | {
      kind: "ready";
      view: IndustryHierarchyView;
      pendingInstrument?: string;
      refreshError?: string;
    };

export function IndustryHierarchyExplorer({
  snapshot,
  asOf,
  parentCode,
  parentName,
  onBack,
  onRefresh,
  refreshing,
}: {
  snapshot: RotationSnapshot;
  asOf: string;
  parentCode: string;
  parentName: string;
  onBack: () => void;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const [allL2, setAllL2] = useState(false);
  const [l2Code, setL2Code] = useState(() =>
    new URLSearchParams(window.location.search).get("l2") ?? "");
  const [instrument, setInstrument] = useState(() =>
    new URLSearchParams(window.location.search).get("stock") ?? "");
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const lastView = useRef<IndustryHierarchyView | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  useEffect(() => {
    const url = hierarchyUrl(snapshot, asOf, parentCode, allL2, l2Code, instrument);
    const retained = canRetainStockWorkbench(lastView.current, l2Code);
    let active = true;
    setLoad(retained
      ? { kind: "ready", view: retained, pendingInstrument: instrument }
      : { kind: "loading" });
    loadHierarchy(url)
      .then((view) => {
        if (!active) return;
        const stableView = retainNavigationEvidence(retained, view);
        lastView.current = stableView;
        setLoad({ kind: "ready", view: stableView });
      })
      .catch((error: unknown) => {
        if (!active) return;
        const message = error instanceof Error ? error.message : "未知错误";
        setLoad(retained
          ? { kind: "ready", view: retained, refreshError: message }
          : { kind: "error", message });
      });
    return () => {
      active = false;
    };
  }, [
    allL2,
    asOf,
    instrument,
    l2Code,
    parentCode,
    reloadVersion,
    snapshot.data_snapshot_id,
  ]);
  const retry = () => {
    clearHierarchyRequests();
    setReloadVersion((value) => value + 1);
    onRefresh();
  };
  const selectL2 = (code: string) => {
    setL2Code(code);
    setInstrument("");
    replaceHierarchyUrl(code, "");
  };
  const selectInstrument = (code: string) => {
    setInstrument(code);
    if (code === instrument) setReloadVersion((value) => value + 1);
    replaceHierarchyUrl(l2Code, code);
  };
  const backToL1 = () => {
    replaceHierarchyUrl("", "");
    onBack();
  };

  return (
    <section className="hierarchy-explorer" aria-label="行业层级下钻">
      <nav className="hierarchy-breadcrumb" aria-label="行业层级">
        <button onClick={backToL1} type="button">一级行业</button>
        <span>›</span><strong>{parentName}</strong>
        {l2Code ? <><span>›</span><strong>{l2Code}</strong></> : null}
      </nav>
      {load.kind === "loading" ? <HierarchyState title="正在读取同一快照" /> : null}
      {load.kind === "error" ? (
        <HierarchyState title="层级数据读取失败" detail={load.message} />
      ) : null}
      {load.kind === "ready" && load.view.status === "blocked" ? (
        <BlockedHierarchyState
          onRefresh={retry}
          refreshing={refreshing}
          view={load.view}
        />
      ) : null}
      {load.kind === "ready" && load.view.status === "ready" ? (
        <HierarchyReady
          allL2={allL2}
          instrument={instrument}
          onAllL2={(value) => {
            setAllL2(value);
            setL2Code("");
            setInstrument("");
            replaceHierarchyUrl("", "");
          }}
          onInstrument={selectInstrument}
          onL2={selectL2}
          pendingInstrument={load.pendingInstrument}
          refreshError={load.refreshError}
          view={load.view}
        />
      ) : null}
    </section>
  );
}

function HierarchyReady({
  view,
  allL2,
  instrument,
  onAllL2,
  onL2,
  onInstrument,
  pendingInstrument,
  refreshError,
}: {
  view: IndustryHierarchyView;
  allL2: boolean;
  instrument: string;
  onAllL2: (value: boolean) => void;
  onL2: (code: string) => void;
  onInstrument: (code: string) => void;
  pendingInstrument?: string;
  refreshError?: string;
}) {
  if (view.level === "stock") {
    return <div className="hierarchy-ready hierarchy-ready--stock">
      <header>
        <div><small>准确比较集合</small><strong>{view.benchmark_id}</strong></div>
        <span>{view.as_of} · {view.nodes.length} 个对象</span>
      </header>
      <StockHierarchyWorkbench
        onInstrument={onInstrument}
        pendingInstrument={pendingInstrument}
        refreshError={refreshError}
        view={view}
      />
      <p className="hierarchy-readonly">只读研究排序，不是个股推荐，不产生订单。</p>
    </div>;
  }
  return <div className="hierarchy-ready">
    <header>
      <div><small>准确比较集合</small><strong>{view.benchmark_id}</strong></div>
      {view.level === "L2" ? <label>
        <input checked={allL2} onChange={(event) => onAllL2(event.target.checked)}
          type="checkbox" />全部 L2
      </label> : null}
      <span>{view.as_of} · {view.nodes.length} 个对象</span>
    </header>
    <HierarchyRotationWorkbench
      onSelect={view.level === "L2" ? onL2 : onInstrument}
      selectedCode={instrument}
      view={view}
    />
    <p className="hierarchy-readonly">只读研究排序，不是个股推荐，不产生订单。</p>
  </div>;
}

function BlockedHierarchyState({
  view,
  onRefresh,
  refreshing,
}: {
  view: IndustryHierarchyView;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const message = describeHierarchyBlock(view);
  return <HierarchyState
    action={<button disabled={refreshing} onClick={onRefresh} type="button">
      {refreshing ? "刷新中…" : "刷新当前快照"}
    </button>}
    detail={message.detail}
    technical={<TechnicalDetails entries={[
      { label: "缺口代码", value: view.known_gaps },
    ]} />}
    title={message.title}
  />;
}

function HierarchyState({
  title,
  detail,
  action,
  technical,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
  technical?: ReactNode;
}) {
  return <div className="hierarchy-state"><h2>{title}</h2>
    <p>{detail ?? "正在读取分类、历史成员、指数和行情证据。"}</p>
    {action}
    {technical}
    <strong>不会使用 L1 或当前成员替代缺失数据。</strong></div>;
}
