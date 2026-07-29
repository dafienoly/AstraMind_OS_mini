import type { RealtimeMarketProjection } from "./types";

export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private readonly listeners = new Map<string, EventListener>();

  constructor(readonly url: string | URL) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, listener);
  }

  emit(type: string, payload: object) {
    this.listeners.get(type)?.({
      data: JSON.stringify(payload),
    } as MessageEvent<string>);
  }

  close() {
    this.closed = true;
  }
}

export function realtimeProjection(): RealtimeMarketProjection {
  const now = new Date().toISOString();
  return {
    projection_id: `sha256:${"5".repeat(64)}`,
    provider: "miniqmt",
    session_id: `sha256:${"6".repeat(64)}`,
    state: "current",
    transport_health: "connected",
    market_session: "continuous_auction",
    daily_data_state: "current",
    operational_state: "updating",
    as_of: now,
    latest_completed_trade_date: "2026-07-29",
    latest_trading_date: "2026-07-30",
    latest_received_at: now,
    latest_market_time_ms: Date.now() - 180,
    granularity_ms: 1000,
    quote_count: 5006,
    breadth_observed: 5000,
    breadth_expected: 5000,
    breadth_coverage_ratio: 1,
    advancing: 3200,
    declining: 1800,
    unchanged: 100,
    total_amount: 900_000_000_000,
    indexes: [{
      instrument_id: "000300.SH",
      last_price: 4032.18,
      change_percent: 0.73,
      market_time_ms: Date.now() - 180,
    }],
    industries: [{
      industry_code: "801001.SI",
      change_percent: 1.82,
      observed_constituents: 20,
    }],
    known_gaps: [],
  };
}
