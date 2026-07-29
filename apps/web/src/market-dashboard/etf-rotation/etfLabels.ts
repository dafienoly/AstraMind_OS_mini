import type { EtfRotationCandidate } from "../types";

const stateLabels: Record<EtfRotationCandidate["state"], string> = {
  eligible: "通过研究门禁",
  context_only: "仅作上下文",
  rejected: "证据未通过",
  stale: "日线待更新",
  unavailable: "当前不可用",
};

const reasonLabels: Record<string, string> = {
  mapping_not_effective_at_as_of: "映射在快照时点尚未生效",
  mapping_unavailable: "该行业暂无可用 ETF 映射",
  latest_bar_before_decision_cutoff: "ETF 日线早于本次决策截止日",
  latest_bar_before_cutoff: "ETF 日线早于决策截止日",
  spread_proxy_above_35bp: "OHLC 价差代理高于 35 bp",
  tracking_proxy_above_12pct: "相对申万 L1 跟踪偏离高于 12%",
  tracking_proxy_unavailable: "跟踪偏离证据不足",
  price_structure_below_60: "价格结构未确认",
  overall_score_below_60: "综合分低于 60",
  completed_sessions_below_252: "上市历史不足 252 个完成交易日",
  median_amount_20d_below_20m: "近 20 日成交额不足 2,000 万元",
  latest_size_below_100m: "最新估算规模不足 1 亿元",
};

const mappingLabels: Record<string, string> = {
  exact: "行业精确映射",
  subindustry: "仅覆盖部分子行业，只作背景参考",
  composite_proxy: "综合代理，行业暴露不纯，只作背景参考",
  theme_context: "主题相关 ETF，并非行业精确映射，只作背景参考",
  unavailable: "该行业暂无可用 ETF 映射",
};

export function etfCandidateStateLabel(state: EtfRotationCandidate["state"]) {
  return stateLabels[state];
}

export function etfRejectionReasonLabel(value: string) {
  if (value.startsWith("mapping_tier:")) {
    return mappingLabels[value.slice("mapping_tier:".length)]
      ?? "ETF 映射口径尚未识别";
  }
  return reasonLabels[value] ?? value;
}
