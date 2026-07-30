import type { MarketModelFamily } from "../market-dashboard/model-evidence/types";

export interface MethodCatalogEntry {
  family: MarketModelFamily;
  label: string;
  shortLabel: string;
  v1: string;
  v2: string;
  target: string;
  dataGate: string;
}

export const methodCatalog: readonly MethodCatalogEntry[] = [
  {
    family: "industry_heat",
    label: "行业热力",
    shortLabel: "热力",
    v1: "相对强弱、上涨广度与成交结构规则评分",
    v2: "学习行业未来相对收益，不改写原始结构证据",
    target: "未来 1 / 5 日行业相对中证全指超额收益",
    dataGate: "生产历史特征矩阵与月度训练输入",
  },
  {
    family: "industry_rotation",
    label: "相对轮动",
    shortLabel: "轮动",
    v1: "相对强弱、相对动量与四象限迁移",
    v2: "学习行业中期相对收益，保留价格代理边界",
    target: "未来 5 / 20 日行业相对中证全指超额收益",
    dataGate: "点时行业成员与完整相对收益历史",
  },
  {
    family: "industry_lifecycle",
    label: "生命周期",
    shortLabel: "生命周期",
    v1: "趋势、位置与参与度共同判定六阶段",
    v2: "学习六阶段概率与置信度，不覆盖规则结果",
    target: "未来行业六阶段概率与置信度",
    dataGate: "严格点时行业成员与生命周期历史",
  },
  {
    family: "industry_research_ranking",
    label: "行业内研究顺序",
    shortLabel: "行业排序",
    v1: "质量、动量、结构与风险固定权重排序",
    v2: "学习行业内相对收益，只安排研究优先级",
    target: "未来 20 / 60 日行业内相对收益",
    dataGate: "严格点时行业归属与可比较股票历史",
  },
  {
    family: "etf_rotation",
    label: "ETF 轮动",
    shortLabel: "ETF",
    v1: "收益、风险、流动性与价差门组成研究漏斗",
    v2: "学习成本后超额，仍不直接形成组合或订单",
    target: "未来 20 日相对官方跟踪基准的成本后超额",
    dataGate: "点时映射、官方基准、NAV 与 60 日真实 L1 价差",
  },
];

export function catalogEntry(family: MarketModelFamily) {
  return methodCatalog.find((entry) => entry.family === family) ?? methodCatalog[0];
}
