import { useEffect, useState } from "react";

import { stockWorkbenchHref } from "../stock-workbench/focus";
import { fetchIndustryRanking } from "./marketDashboardClient";
import type {
  IndustryResearchRankingSnapshot,
  IndustryResearchRow,
} from "./types";
import { ModelEvidenceBand } from "./model-evidence/ModelEvidenceBand";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; value: IndustryResearchRankingSnapshot };

export function IndustryRankingPanel({
  dataSnapshotId,
  industryCode,
  lifecycleCutoff,
  taxonomyVersion,
}: {
  dataSnapshotId: string;
  industryCode: string;
  lifecycleCutoff: string | null;
  taxonomyVersion: string | null;
}) {
  const restored = new URLSearchParams(window.location.search).get("rankingStock") ?? undefined;
  const [selected, setSelected] = useState<string | undefined>(restored);
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    fetchIndustryRanking(dataSnapshotId, industryCode, selected, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        if (
          value.data_snapshot_id !== dataSnapshotId
          || value.evidence_cutoff !== lifecycleCutoff
          || value.taxonomy_version !== taxonomyVersion
        ) {
          setState({ kind: "error", message: "排序与生命周期证据身份不一致" });
          return;
        }
        setState({ kind: "ready", value });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            kind: "error",
            message: error instanceof Error ? error.message : "未知错误",
          });
        }
      });
    return () => controller.abort();
  }, [dataSnapshotId, industryCode, lifecycleCutoff, selected, taxonomyVersion]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (selected) url.searchParams.set("rankingStock", selected);
    else url.searchParams.delete("rankingStock");
    window.history.replaceState(null, "", url);
  }, [selected]);

  if (state.kind !== "ready") {
    return <section className="ranking-state" aria-live="polite">
      <strong>{state.kind === "loading" ? "正在形成行业内研究顺序" : "研究排序暂不可用"}</strong>
      <span>{state.kind === "loading" ? "只读取同一正式快照。" : state.message}</span>
    </section>;
  }
  if (state.value.status === "blocked" || state.value.rows.length === 0) {
    return <section className="ranking-state">
      <strong>当前行业没有可比较的点时样本</strong>
      <code>{state.value.known_gaps.join(" · ")}</code>
    </section>;
  }
  return <RankingWorkspace
    value={state.value}
    onSelect={setSelected}
  />;
}

function RankingWorkspace({
  value,
  onSelect,
}: {
  value: IndustryResearchRankingSnapshot;
  onSelect: (value: string) => void;
}) {
  const selected = value.rows.find(
    (item) => item.instrument_id === value.selected_instrument_id,
  ) ?? value.rows[0];
  return <section className="ranking-workspace" aria-label="行业内个股研究排序">
    <header>
      <div>
        <p className="eyebrow">行业内研究顺序 · {value.evidence_cutoff}</p>
        <h2>{value.industry_name} · {value.lifecycle_stage}</h2>
      </div>
      <p>{value.covered_member_count}/{value.member_count} 达到 60% 覆盖 · 未经独立样本外验证</p>
    </header>
    <ModelEvidenceBand
      compact
      dataCutoff={value.evidence_cutoff}
      family="industry_research_ranking"
      horizons={["未来 20 日", "未来 60 日"]}
    />
    <div className="ranking-layout">
      <div className="ranking-table-scroll">
        <table className="ranking-table">
          <thead><tr>
            <th>研究对象</th><th>标签</th><th>综合</th><th>事件/情绪</th>
            <th>技术/量价</th><th>基本面上下文</th><th>风险</th><th>反转约束</th><th>覆盖</th>
          </tr></thead>
          <tbody>{value.rows.map((row) => <RankingRow
            key={row.instrument_id}
            row={row}
            selected={row.instrument_id === selected.instrument_id}
            onSelect={onSelect}
          />)}</tbody>
        </table>
      </div>
      <aside className="ranking-inspector">
        <div>
          <p className="eyebrow">统一个股证据入口</p>
          <h3>{selected.instrument_name} <small>{selected.instrument_id}</small></h3>
          <span>{selected.research_label} · 综合 {score(selected.overall_priority)}</span>
        </div>
        <p>排序页只保留同业比较；完整 K 线、分钟成交、五档盘口与估值证据由通用个股工作面呈现。</p>
        <a href={stockWorkbenchHref(selected.instrument_id, {
          origin: "industry_ranking",
          mode: "completed",
          returnTarget: "industry_ranking",
          dataSnapshotId: value.data_snapshot_id,
          asOf: value.evidence_cutoff ?? undefined,
          industryCode: value.industry_code,
        })}>打开通用个股工作面 →</a>
        <details><summary>方法与缺口</summary>
          <code>{value.scoring_definition_version}</code>
          <p>{selected.known_gaps.join(" · ") || "分项覆盖完整"}</p>
          <p>排序用于安排研究顺序，不是买卖、组合或订单。</p>
        </details>
      </aside>
    </div>
  </section>;
}

function RankingRow({
  row,
  selected,
  onSelect,
}: {
  row: IndustryResearchRow;
  selected: boolean;
  onSelect: (value: string) => void;
}) {
  return <tr aria-selected={selected} onClick={() => onSelect(row.instrument_id)}>
    <td><button type="button"><strong>{row.instrument_name}</strong>
      <small>{row.instrument_id}</small></button></td>
    <td><span className="research-label" data-label={row.research_label}>
      {row.research_label}</span></td>
    {[row.overall_priority, row.event_sentiment_score, row.technical_volume_score,
      row.fundamental_score, row.risk_score, row.reversal_repair_score].map((value, index) => (
      <td key={index}>{score(value)}</td>
    ))}
    <td>{(row.coverage * 100).toFixed(0)}%</td>
  </tr>;
}

function score(value: number | null) {
  return value === null ? "—" : value.toFixed(1);
}
