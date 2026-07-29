import { useState } from "react";

import type { MarketModelFamily, MarketModelStatusItem } from "./types";
import { useMarketModelStatus } from "./useMarketModelStatus";

export function ModelEvidenceBand({
  family,
  horizons,
  dataCutoff,
  compact = false,
}: {
  family: MarketModelFamily;
  horizons: string[];
  dataCutoff: string | null;
  compact?: boolean;
}) {
  const { state, refresh } = useMarketModelStatus(family);
  const [horizon, setHorizon] = useState(horizons[0] ?? "当前");
  const [methodOpen, setMethodOpen] = useState(false);
  if (state.kind === "loading") {
    return <section className="model-evidence-band is-loading" aria-live="polite">
      <div><small>方法与证据</small><strong>正在读取模型身份与证据</strong></div>
      <span>数据截止 {dataCutoff ?? "读取中"}</span>
    </section>;
  }
  if (state.kind === "error") {
    return <section className="model-evidence-band is-error" aria-live="polite">
      <div><small>方法状态不可用</small><strong>页面原始证据仍保持可读</strong></div>
      <span>{modelStatusErrorLabel(state.message)}</span>
      <button onClick={refresh} type="button">重试模型状态</button>
    </section>;
  }
  const { item } = state;
  const fallback = item.state === "fallback_v1" || item.state === "blocked";
  return <section
    aria-label={`${item.display_name}方法与证据`}
    className={`model-evidence-band${compact ? " is-compact" : ""}`}
    data-state={item.state}
  >
    <div className="model-evidence-identity">
      <small>{item.display_name} · 当前方法</small>
      <strong>{item.method_version}</strong>
      <span>{stateLabel(item)}</span>
    </div>
    <div className="model-evidence-periods" aria-label="预测周期与结构">
      <small>预测周期</small>
      <div>
        {horizons.map((value) => <button
          aria-pressed={!fallback && horizon === value}
          disabled={fallback}
          key={value}
          onClick={() => setHorizon(value)}
          type="button"
        >{value}</button>)}
        <button aria-pressed={fallback} className="raw-structure" type="button">
          原始结构
        </button>
      </div>
    </div>
    <div className="model-evidence-summary">
      <small>证据与截止</small>
      <strong>{evidenceLabel(item)}</strong>
      <span>训练截止 {trainingCutoff(item)} · 数据截止 {dataCutoff ?? "未知"}</span>
    </div>
    <button
      aria-expanded={methodOpen}
      className="model-evidence-method"
      onClick={() => setMethodOpen((value) => !value)}
      type="button"
    >{methodOpen ? "收起方法" : "查看方法"}</button>
    {methodOpen ? <div className="model-evidence-detail">
      <div>
        <small>准确身份</small>
        <code>{item.manifest_id ?? item.method_version}</code>
      </div>
      <div>
        <small>证据身份</small>
        <code>{item.evidence_bundle_id ?? "尚无支持性证据包"}</code>
      </div>
      <div>
        <small>回退 / 阻断原因</small>
        <p>{item.reason_codes.length
          ? item.reason_codes.map(reasonLabel).join("；")
          : "当前没有已记录的回退原因"}</p>
      </div>
      <div>
        <small>只读边界</small>
        <p>只解释市场研究，不创建组合、订单或券商动作。</p>
      </div>
    </div> : null}
    {fallback ? <p className="model-evidence-fallback">
      v2 尚未形成可展示结果，当前准确显示规则式 v1；没有用模拟预测填充。
      {item.reason_codes.length ? ` 原因：${item.reason_codes.map(reasonLabel).join("；")}` : ""}
    </p> : null}
  </section>;
}

function stateLabel(item: MarketModelStatusItem) {
  if (item.state === "active_v2") return "支持性证据通过";
  if (item.state === "unvalidated_v2") return "未完成封存验证";
  if (item.state === "blocked") return "证据门阻断";
  return "已回退规则式 v1";
}

function evidenceLabel(item: MarketModelStatusItem) {
  if (item.evidence_state === "supported") return "支持性证据通过";
  if (item.evidence_state === "unvalidated") return "正确性通过 · OOS 待完成";
  if (item.evidence_state === "unsupported") return "封存证据不支持";
  if (item.evidence_state === "development_only") return "仅开发证据";
  return "支持性证据尚未形成";
}

function trainingCutoff(item: MarketModelStatusItem) {
  if (item.state === "fallback_v1") return "规则式 · 不适用";
  return item.effective_at ? `${item.effective_at.slice(0, 10)} 前已生效` : "未由状态接口发布";
}

const reasonLabels: Record<string, string> = {
  v2_not_trained: "v2 尚未训练",
  v2_activation_invalid: "v2 激活记录无效",
  v2_referenced_artifact_invalid: "v2 产物或内容身份损坏",
  historical_breadth_membership_not_then_known: "历史行业广度成员并非当时已知",
  historical_membership_not_then_known: "历史行业成员并非当时已知",
  official_benchmark_mapping_not_then_known: "ETF 官方基准映射缺少历史可用时点",
};

function reasonLabel(value: string) {
  if (reasonLabels[value]) return reasonLabels[value];
  const spread = value.match(/^l1_spread_sessions:(\d+)\/60$/);
  if (spread) return `真实 L1 价差已累计 ${spread[1]}/60 个交易日`;
  return value.replaceAll("_", " ");
}

function modelStatusErrorLabel(message: string) {
  const normalized = message.toLowerCase();
  if (normalized.includes("abort") || normalized.includes("signal")) {
    return "模型状态请求已中断，请重试";
  }
  return message;
}
