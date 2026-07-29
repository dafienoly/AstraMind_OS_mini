import { TechnicalDetails } from "../business-language/TechnicalDetails";
import { marketBusinessText } from "../business-language/marketBusinessText";

import type { RealtimeMarketView } from "./useRealtimeMarket";

export function RealtimePulse({ view }: { view: RealtimeMarketView }) {
  const projection = view.projection;
  const label = stateLabel(view);
  const operationalState = semanticState(view);
  const latency = renderLatencyMs(projection?.latest_received_at);
  return <section
    aria-label="盘中会话脉冲"
    aria-live="polite"
    className="realtime-pulse"
    data-e2e-latency-ms={latency ?? undefined}
    data-received-at={projection?.latest_received_at ?? undefined}
    data-state={operationalState}
  >
    <div className="realtime-pulse__headline">
      <strong>盘中会话脉冲</strong>
      <em>{label}</em>
      <span>完成日事实保持不变</span>
    </div>
    <dl>
      <PulseValue label="市场时间" value={formatMarketTime(projection?.latest_market_time_ms)} />
      <i aria-hidden="true" />
      <PulseValue label="接收时间" value={formatTime(projection?.latest_received_at)} />
      <PulseValue
        label="完成日"
        value={projection?.latest_completed_trade_date ?? "待确认"}
      />
      <PulseValue
        label="传输"
        value={projection?.transport_health === "connected" ? "连接正常" : "连接中断"}
      />
      <PulseValue label="页面延迟" value={latency === null ? "—" : `${latency} ms`} />
      <PulseValue
        label="粒度"
        value={projection ? `${projection.granularity_ms / 1000} 秒` : "—"}
      />
      <PulseValue label="覆盖" value={coverage(projection)} />
      <PulseValue label="会话" value={projection ? "实时会话已建立" : "待确认"} />
    </dl>
    <TechnicalDetails entries={[
      { label: "会话身份", value: projection?.session_id },
      { label: "投影身份", value: projection?.projection_id },
      { label: "提供方路由", value: projection?.provider },
      { label: "缺口代码", value: projection?.known_gaps },
    ]} />
    {view.message ? <p>{view.message}</p> : null}
  </section>;
}

function PulseValue({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return <div>
    <dt>{label}</dt>
    <dd className={mono ? "mono" : undefined}>{value}</dd>
  </div>;
}

function stateLabel(view: RealtimeMarketView) {
  if (view.phase === "loading") return "正在连接";
  if (view.phase === "empty") return "等待 MiniQMT 会话";
  if (view.phase === "error") return "实时区域不可用";
  return marketBusinessText(semanticState(view));
}

function semanticState(view: RealtimeMarketView) {
  if (view.effectiveState === "disconnected") return "disconnected";
  return view.projection?.operational_state ?? "unknown";
}

function coverage(projection: RealtimeMarketView["projection"]) {
  if (!projection) return "—";
  if (projection.breadth_expected === null) {
    return `${projection.breadth_observed} 只`;
  }
  const percent = projection.breadth_coverage_ratio === null
    ? "—"
    : `${(projection.breadth_coverage_ratio * 100).toFixed(1)}%`;
  return `${projection.breadth_observed} / ${projection.breadth_expected} · ${percent}`;
}

function renderLatencyMs(receivedAt: string | null | undefined) {
  if (!receivedAt) return null;
  return Math.max(0, Date.now() - Date.parse(receivedAt));
}

function formatMarketTime(value: number | null | undefined) {
  if (!value || value < 1_000_000_000_000) return "—";
  return formatTime(new Date(value).toISOString(), true);
}

function formatTime(value: string | null | undefined, milliseconds = false) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    ...(milliseconds ? { fractionalSecondDigits: 3 } : {}),
  }).format(new Date(value));
}
