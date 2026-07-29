import type { EtfRotationCandidate, EtfRotationProjection } from "../types";
import { etfRejectionReasonLabel } from "./etfLabels";

export function EtfInspector({
  candidate,
  projection,
}: {
  candidate: EtfRotationCandidate | null;
  projection: EtfRotationProjection;
}) {
  return <aside className="etf-inspector">
    <p className="eyebrow">价格结构核验</p>
    <h2>{candidate?.price_conclusion ?? "尚无可核验证据"}</h2>
    <dl>
      <Metric label="近 20 日" value={percent(candidate?.return_20d)} />
      <Metric
        label="20 日成交额"
        value={amount(candidate?.median_amount_20d_cny)}
      />
      <Metric
        label="OHLC 价差代理"
        value={bps(candidate?.spread_proxy_bps)}
        note={`门槛 ≤ ${projection.spread_proxy_threshold_bps} bp`}
      />
      <Metric
        label="申万 L1 跟踪偏离"
        value={percent(candidate?.tracking_error_60d)}
        note={`门槛 ≤ ${(projection.tracking_proxy_threshold * 100).toFixed(0)}%`}
      />
    </dl>
    <section className="etf-reasons">
      <strong>当前结论</strong>
      {candidate?.rejection_reasons.length
        ? <ul>{candidate.rejection_reasons.map((reason) => <li key={reason}>
          {etfRejectionReasonLabel(reason)}
        </li>)}</ul>
        : <p>当前研究代理门禁通过；仍不是组合或订单。</p>}
    </section>
    <section className="etf-target-summary">
      <strong>目标草案</strong>
      <span>ETF 暴露 {(1 - projection.target_draft.cash_weight) * 100}%</span>
      <span>现金 {projection.target_draft.cash_weight * 100}%</span>
      <button disabled type="button">公共组合目标未授权</button>
    </section>
  </aside>;
}

function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return <div><dt>{label}</dt><dd>{value}</dd>{note ? <small>{note}</small> : null}</div>;
}

function percent(value: number | null | undefined) {
  return value == null ? "—" : `${(value * 100).toFixed(2)}%`;
}

function bps(value: number | null | undefined) {
  return value == null ? "—" : `${value.toFixed(1)} bp`;
}

function amount(value: number | null | undefined) {
  return value == null ? "—" : `${(value / 100_000_000).toFixed(2)} 亿元`;
}
