import { TechnicalDetails } from "../business-language/TechnicalDetails";
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
    <i /><strong>数据版本</strong> 更新至 {projection.evidence_cutoff ?? "未知"}
    <i /><strong>投影</strong> {projection.projection_version}
    <TechnicalDetails entries={[
      { label: "数据快照身份", value: projection.data_snapshot_id },
      { label: "缺口代码", value: projection.known_gaps },
    ]} />
    <em>市场观察，不是买卖信号</em>
  </div>;
}
