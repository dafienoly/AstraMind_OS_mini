import { useMemo } from "react";
import type { ReactNode } from "react";

import type { StockEvidence } from "./rotationTypes";
import { stockEvidenceAtDate } from "./stockEvidenceTimeline";

export function StockEvidencePanel({
  evidence,
  hoverDate,
  updatingLabel,
}: {
  evidence: StockEvidence | null;
  hoverDate: string;
  updatingLabel?: string;
}) {
  const selected = useMemo(
    () => evidence ? stockEvidenceAtDate(evidence, hoverDate) : null,
    [evidence, hoverDate],
  );
  if (!evidence) {
    return <aside className="stock-evidence-panel" aria-label="股票证据">
      {updatingLabel ? (
        <div className="stock-local-loading stock-local-loading--evidence" aria-hidden="true">
          <span className="stock-loading-mark" />
          <strong>{updatingLabel}</strong>
          <small>正在读取基本面与集中趋势</small>
        </div>
      ) : null}
      <h3>股票证据不可用</h3>
      <p className="stock-evidence-gap">当前响应没有同快照基本面证据。</p>
    </aside>;
  }
  const fundamental = selected?.fundamental ?? null;
  const holder = selected?.shareholder ?? evidence.shareholder_concentration;
  return <aside className="stock-evidence-panel" aria-label="股票证据">
    {updatingLabel ? (
      <div className="stock-local-loading stock-local-loading--evidence" aria-hidden="true">
        <span className="stock-loading-mark" />
        <strong>{updatingLabel}</strong>
        <small>正在读取基本面与集中趋势</small>
      </div>
    ) : null}
    <p className="eyebrow">股票证据</p>
    <h3>基本面与集中趋势</h3>
    <small>{hoverDate} · 悬浮日点时证据 · 同一快照</small>
    <EvidenceGroup title="估值与规模">
      <EvidenceRow label="PE (TTM)" value={multiple(fundamental?.price_earnings_ttm)} />
      <EvidenceRow label="PB" value={multiple(fundamental?.price_book)} />
      <EvidenceRow label="总市值" value={currency(fundamental?.total_market_value_cny)} />
      <EvidenceRow
        label="流通市值"
        value={currency(fundamental?.circulating_market_value_cny)}
      />
    </EvidenceGroup>
    <EvidenceGroup title="交易与价格">
      <EvidenceRow label="最新收盘" value={number(fundamental?.latest_close)} />
      <EvidenceRow
        direction={fundamental?.percent_change}
        label="当日涨跌"
        value={percentPoints(fundamental?.percent_change)}
      />
      <EvidenceRow label="换手率" value={percentPoints(fundamental?.turnover_rate)} />
      <EvidenceRow label="成交额" value={currency(fundamental?.amount_cny)} />
      <p className="stock-evidence-time">
        行情/估值：{fundamental?.available_at.slice(0, 16).replace("T", " ") ?? "未纳入"}
      </p>
    </EvidenceGroup>
    <EvidenceGroup title="股东集中趋势">
      <EvidenceRow label="最新股东户数" value={integer(holder.holder_count)} />
      <EvidenceRow
        direction={holder.change_rate === null ? null : -holder.change_rate}
        label="较上期变化"
        value={holderDirection(holder)}
      />
      <EvidenceRow
        label="连续方向"
        value={holder.status === "ready"
          ? `连续 ${holder.consecutive_periods} 期`
          : "不可计算"}
      />
      <EvidenceRow
        label="公告 / 报告期"
        value={holder.announced_on && holder.reporting_period
          ? `${holder.announced_on} / ${holder.reporting_period}`
          : "—"}
      />
      <EvidenceRow
        label="观察年龄"
        value={holder.observation_age_days === null
          ? "—"
          : `${holder.observation_age_days} 天`}
      />
      {holder.status !== "ready" ? (
        <p className="stock-evidence-gap">{holderGap(holder.known_gaps)}</p>
      ) : null}
      <p className="stock-evidence-boundary">
        股东户数集中趋势，不代表真实筹码峰、持仓账户分布或成本。
      </p>
    </EvidenceGroup>
    <details>
      <summary>数据与口径</summary>
      <code>{evidence.known_gaps.join("、") || "当前字段无已知缺口"}</code>
    </details>
  </aside>;
}

function EvidenceGroup({ title, children }: { title: string; children: ReactNode }) {
  return <section><h4>{title}</h4>{children}</section>;
}

function EvidenceRow({
  label,
  value,
  direction,
}: {
  label: string;
  value: string;
  direction?: number | null;
}) {
  return <div className="stock-evidence-row">
    <span>{label}</span>
    <strong className={direction == null ? "" : direction >= 0 ? "is-up" : "is-down"}>
      {value}
    </strong>
  </div>;
}

function number(value: number | null | undefined) {
  return value == null ? "—" : value.toFixed(2);
}

function multiple(value: number | null | undefined) {
  return value == null ? "—" : `${value.toFixed(2)}×`;
}

function integer(value: number | null | undefined) {
  return value == null ? "—" : value.toLocaleString("zh-CN");
}

function currency(value: number | null | undefined) {
  if (value == null) return "—";
  return value >= 100_000_000
    ? `${(value / 100_000_000).toFixed(2)} 亿元`
    : `${(value / 10_000).toFixed(2)} 万元`;
}

function percentPoints(value: number | null | undefined) {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}% ${value >= 0 ? "↑" : "↓"}`;
}

function percentRatio(value: number | null | undefined) {
  if (value == null) return "—";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}% ${value >= 0 ? "↑" : "↓"}`;
}

function holderDirection(holder: StockEvidence["shareholder_concentration"]) {
  if (holder.change_rate === null || holder.direction === null) return "不可计算";
  const label = holder.direction === "concentrating"
    ? "集中 ↑"
    : holder.direction === "dispersing" ? "分散 ↓" : "持平";
  return `${percentRatio(holder.change_rate)} · ${label}`;
}

function holderGap(gaps: string[]) {
  if (gaps.includes("shareholder_count_not_in_snapshot")) {
    return "股东户数未纳入当前数据快照；不会跨快照补齐。";
  }
  if (gaps.includes("shareholder_count_previous_period_unavailable")) {
    return "只有一期股东户数，暂时不能计算集中方向。";
  }
  return "当前股票没有可用的点时股东户数。";
}
