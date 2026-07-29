import type { MarketDashboardProjection } from "./types";

export function MarketStatusStrip({
  projection,
  refreshing,
  onRefresh,
}: {
  projection: MarketDashboardProjection;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const state = projection.status === "ready" ? "current" : projection.status;
  return <div className="rotation-status" data-state={state}>
    <strong>数据</strong> {projection.evidence_cutoff ?? "无共同截止日"}
    {projection.status === "ready" ? " 快照内完整" : ` ${projection.status === "stale" ? "已陈旧" : "已阻断"}`}
    <button disabled={refreshing} onClick={onRefresh} type="button">
      {refreshing ? "刷新中…" : "刷新快照"}
    </button>
    {projection.status !== "ready" ? <a href="/system">查看恢复状态</a> : null}
    <i /><strong>快照</strong> {shortIdentity(projection.data_snapshot_id)}
    <i /><strong>投影</strong> {projection.projection_version}
    <em>市场观察，不是买卖信号</em>
  </div>;
}

function shortIdentity(value: string) {
  return value.length > 22 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value;
}
