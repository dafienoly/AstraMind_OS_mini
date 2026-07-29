import type { EtfRotationProjection } from "../types";

export function EtfFunnel({ value }: { value: EtfRotationProjection["funnel"] }) {
  const stages = [
    ["行业身份", value.industry_count],
    ["行业精确映射", value.exact_mapping_count],
    ["基础资格", value.foundation_count],
    ["代理门禁", value.evidence_gate_count],
    ["目标候选", value.eligible_count],
  ] as const;
  return <section className="etf-funnel" aria-label="ETF 方向漏斗">
    <header>
      <strong>方向漏斗</strong>
      <span>每一步保留淘汰原因</span>
    </header>
    <ol>
      {stages.map(([label, count], index) => <li key={label}>
        <small>{label}</small>
        <strong>{count}</strong>
        {index < stages.length - 1 ? <i aria-hidden="true">→</i> : null}
      </li>)}
    </ol>
  </section>;
}
