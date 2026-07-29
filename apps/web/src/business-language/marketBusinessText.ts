const labels: Record<string, string> = {
  ready: "数据可用",
  unavailable: "暂无可用数据",
  insufficient_history: "历史样本不足",
  eligible: "通过研究门禁",
  context_only: "仅作上下文",
  rejected: "证据未通过",
  blocked: "数据条件未满足",
  stale: "更新延迟",
  current: "正在更新",
  disconnected: "实时连接中断",
  updating: "正在更新",
  update_delayed: "行情更新延迟",
  pre_open: "开盘前 · 最近交易日数据最新",
  lunch_break: "午间休市 · 上午行情已保存",
  closed: "今日已收盘 · 日线数据最新",
  non_trading_day: "市场休市 · 最近交易日数据最新",
  daily_lagging: "日线数据待更新",
  unknown: "行情状态待确认",
  CURRENT: "正在更新",
  STALE: "更新延迟",
  DISCONNECTED: "实时连接中断",
  "date-bound-cutover": "历史行情与实时行情已衔接",
  miniqmt: "MiniQMT 实时行情",
  tushare: "Tushare 历史行情",
  historical_membership_not_then_known:
    "缺少当时可知的历史行业归属，暂不能进行严格历史验证",
  historical_breadth_membership_not_then_known:
    "缺少当时可知的历史行业广度成员，暂不能进行严格历史验证",
  v2_not_trained: "学习模型尚未形成生产结果，当前使用规则模型",
  production_pipeline_unavailable: "生产训练功能尚未接通，当前使用规则模型",
  training_data_blocked: "训练数据条件未满足，当前使用规则模型",
  trained_evidence_insufficient: "学习模型已训练，但样本外证据不足",
  validated_pending_activation: "学习模型已通过验证，等待只读激活",
  active: "学习模型已激活",
  artifact_incompatible: "模型制品损坏或输入版本不兼容，当前使用规则模型",
  active_v2: "学习模型已激活",
  unvalidated_v2: "学习模型尚未完成封存验证",
  fallback_v1: "当前使用规则模型",
  supported: "支持性证据通过",
  unvalidated: "正确性已通过，样本外证据待完成",
  unsupported: "样本外证据不支持",
  development_only: "当前仅有开发证据",
  v2_activation_invalid: "学习模型激活记录无效，当前使用规则模型",
  v2_referenced_artifact_invalid:
    "模型制品损坏或内容身份不一致，当前使用规则模型",
  official_benchmark_mapping_not_then_known:
    "缺少当时可知的 ETF 官方基准映射",
  missing_dataset: "当前数据版本缺少必要数据集",
  industry_member_market_coverage_below_90pct: "行业成员行情覆盖不足 90%",
  insufficient_price_history: "可用价格历史不足",
  insufficient_lifecycle_history: "生命周期历史长度不足",
  insufficient_market_history: "市场历史长度不足",
  member_coverage_below_threshold: "行业成员覆盖未达到计算门槛",
  all_industries_below_coverage: "全部行业的成员覆盖均未达到计算门槛",
  all_industries_below_intraday_coverage: "全部行业的盘中覆盖均未达到计算门槛",
  industry_registry_missing: "行业注册表缺失",
  industry_has_no_eligible_members: "该行业没有可比较的点时样本",
  dashboard_lifecycle_snapshot_mismatch: "大盘与生命周期使用的数据版本不一致",
  snapshot_cutoff_before_as_of_date: "完成日数据早于应有交易日",
  daily_market_instrument_unavailable: "该证券暂无完成日行情",
  shareholder_count_not_in_snapshot: "当前数据版本不含股东户数",
  shareholder_count_instrument_unavailable: "该证券暂无股东户数记录",
  shareholder_count_previous_period_unavailable: "缺少上一期股东户数，暂不能计算变化",
  shareholder_count_not_yet_available_at_hover_date:
    "所选日期尚不能取得该期股东户数",
  sibling_cross_section_below_three: "同层可比较对象不足三项",
  sw2021_pre2021_provider_backcast:
    "2021 年前行业成员属于提供方回溯口径，不作为当时已知事实",
  sw2021_l2_not_published: "二级行业数据尚未发布",
  requested_date_after_snapshot: "请求日期超出当前数据版本截止日",
  same_level_history_incomplete: "同层历史数据不完整",
  research_ranking_not_investment_advice: "研究排序仅用于安排研究顺序",
  price_relative_strength_proxy_not_direct_capital_flow:
    "相对强弱是价格代理，不代表直接资金净流入",
  current_holdings_not_connected: "当前持仓尚未接入研究目标草案",
  research_target_not_portfolio_target: "研究目标草案尚不是正式组合目标",
  point_in_time_lifecycle_history_not_published: "点时生命周期历史尚未发布",
  observed_bid_ask_history_not_published: "真实买卖盘价差历史尚未形成",
  official_tracking_benchmark_history_not_published: "官方跟踪基准历史尚未发布",
  performance_metrics_withheld: "证据条件不足，暂不发布绩效指标",
  etf_mapping_not_effective_at_snapshot_as_of: "ETF 映射在当前数据时点尚未生效",
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
  projection_incomplete: "市场投影数据不完整",
  lifecycle_projection_blocked: "生命周期投影的数据条件未满足",
};

const dynamicLabels: ReadonlyArray<[
  RegExp,
  (match: RegExpMatchArray) => string,
]> = [
  [/^missing_dataset:(.+)$/, () => "当前数据版本缺少必要数据集"],
  [/^missing_datasets:(.+)$/, () => "当前数据版本缺少必要数据集"],
  [/^expected_completed_trade_date[:=](\d{4}-\d{2}-\d{2})$/, (match) =>
    `完成日数据应更新至 ${match[1]}`],
  [/^rotation_blocked:(.+)$/, () => "行业轮动证据条件未满足"],
  [/^stock_rotation_incomplete_panel_excluded:(\d+)(?::.*)?$/, (match) =>
    `有 ${match[1]} 只股票因行情不完整未进入同业比较`],
  [/^mapping_registered_from:(\d{4}-\d{2}-\d{2})$/, (match) =>
    `ETF 映射自 ${match[1]} 起登记可用`],
  [/^l1_spread_sessions:(\d+)\/60$/, (match) =>
    `真实 L1 价差已累计 ${match[1]}/60 个交易日`],
  [/^mapping_tier:exact$/, () => "行业精确映射"],
  [/^mapping_tier:subindustry$/, () => "仅覆盖部分子行业，只作背景参考"],
  [/^mapping_tier:composite_proxy$/, () => "综合代理，行业暴露不纯，只作背景参考"],
  [/^mapping_tier:theme_context$/, () =>
    "主题相关 ETF，并非行业精确映射，只作背景参考"],
  [/^mapping_tier:unavailable$/, () => "该行业暂无可用 ETF 映射"],
];

export const UNKNOWN_BUSINESS_STATE = "暂无法解释的系统状态";

export function marketBusinessText(value: string | null | undefined): string {
  if (!value) return "暂无可用数据";
  if (/^(?:snapshot:)?sha256:[0-9a-f]{32,}$/i.test(value)) return "数据版本";
  if (labels[value]) return labels[value];
  for (const [pattern, describe] of dynamicLabels) {
    const match = value.match(pattern);
    if (match) return describe(match);
  }
  return UNKNOWN_BUSINESS_STATE;
}

export function marketBusinessTexts(values: readonly string[]): string[] {
  return [...new Set(values.map(marketBusinessText))];
}
