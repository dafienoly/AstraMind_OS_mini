import { useState } from "react";

import { TechnicalDetails } from "../../business-language/TechnicalDetails";
import { marketBusinessText } from "../../business-language/marketBusinessText";
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
        <small>回退 / 阻断原因</small>
        <p>{item.reason_codes.length
          ? item.reason_codes.map(marketBusinessText).join("；")
          : "当前没有已记录的回退原因"}</p>
      </div>
      <div>
        <small>只读边界</small>
        <p>只解释市场研究，不创建组合、订单或券商动作。</p>
      </div>
      <TechnicalDetails entries={[
        { label: "准确模型身份", value: item.manifest_id ?? item.method_version },
        {
          label: "证据身份",
          value: item.evidence_bundle_id ?? "尚无支持性证据包",
        },
        { label: "原因代码", value: item.reason_codes },
      ]} />
    </div> : null}
    {fallback ? <p className="model-evidence-fallback">
      学习模型尚未形成可展示结果，当前准确显示规则式 V1；没有用模拟预测填充。
      {item.reason_codes.length
        ? ` 原因：${item.reason_codes.map(marketBusinessText).join("；")}`
        : ""}
    </p> : null}
  </section>;
}

function stateLabel(item: MarketModelStatusItem) {
  return marketBusinessText(item.state);
}

function evidenceLabel(item: MarketModelStatusItem) {
  return marketBusinessText(item.evidence_state);
}

function trainingCutoff(item: MarketModelStatusItem) {
  if (item.state === "fallback_v1") return "规则式 · 不适用";
  return item.effective_at ? `${item.effective_at.slice(0, 10)} 前已生效` : "未由状态接口发布";
}

function modelStatusErrorLabel(message: string) {
  const normalized = message.toLowerCase();
  if (normalized.includes("abort") || normalized.includes("signal")) {
    return "模型状态请求已中断，请重试";
  }
  return message;
}
