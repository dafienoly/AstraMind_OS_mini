export type MarketSessionPhase =
  | "pre_open"
  | "continuous_auction"
  | "lunch_break"
  | "closed"
  | "non_trading_day"
  | "unknown";

export type RealtimeOperationalState =
  | "updating"
  | "update_delayed"
  | "pre_open"
  | "lunch_break"
  | "closed"
  | "non_trading_day"
  | "disconnected"
  | "daily_lagging"
  | "unknown";

export type RealtimeIndexQuote = {
  instrument_id: string;
  last_price: number;
  change_percent: number | null;
  market_time_ms: number | null;
};

export type RealtimeIndustryHeat = {
  industry_code: string;
  change_percent: number;
  observed_constituents: number;
};

export type RealtimeMarketProjection = {
  projection_id: string;
  provider: string;
  session_id: string;
  state: "current" | "stale" | "disconnected";
  transport_health: "connected" | "disconnected";
  market_session: MarketSessionPhase;
  daily_data_state: "current" | "lagging" | "unknown";
  operational_state: RealtimeOperationalState;
  as_of: string;
  latest_completed_trade_date: string | null;
  latest_trading_date: string | null;
  latest_received_at: string | null;
  latest_market_time_ms: number | null;
  granularity_ms: number;
  quote_count: number;
  breadth_observed: number;
  breadth_expected: number | null;
  breadth_coverage_ratio: number | null;
  advancing: number;
  declining: number;
  unchanged: number;
  total_amount: number;
  indexes: RealtimeIndexQuote[];
  industries: RealtimeIndustryHeat[];
  known_gaps: string[];
};

export type RealtimeBookLevel = {
  level: number;
  price: number | null;
  volume: number | null;
};

export type RealtimeInstrumentQuote = {
  instrument_id: string;
  instrument_name: string | null;
  instrument_type: "stock" | "etf" | "index" | "other";
  industry_code: string | null;
  market_time_ms: number | null;
  received_at: string;
  last_price: number | null;
  previous_close: number | null;
  change_percent: number | null;
  open_price: number | null;
  high_price: number | null;
  low_price: number | null;
  volume: number | null;
  amount: number | null;
  upper_limit: number | null;
  lower_limit: number | null;
  stock_status: number | null;
  status_label: string;
  bids: RealtimeBookLevel[];
  asks: RealtimeBookLevel[];
};

export type RealtimeMinuteBar = {
  provider: string;
  session_id: string;
  instrument_id: string;
  minute: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
  observation_count: number;
};

export type RealtimeInstrumentProjection = {
  projection_id: string;
  provider: string;
  session_id: string;
  state: "current" | "stale" | "disconnected";
  as_of: string;
  market_date: string;
  quotes: RealtimeInstrumentQuote[];
  open_minutes: RealtimeMinuteBar[];
  known_gaps: string[];
};

export type RealtimeInstrumentDetail = {
  projection_id: string;
  provider: string;
  session_id: string;
  state: "current" | "stale" | "disconnected";
  as_of: string;
  quote: RealtimeInstrumentQuote;
  minutes: RealtimeMinuteBar[];
  known_gaps: string[];
};

export type RealtimeInstrumentSearchResult = Pick<RealtimeInstrumentQuote,
  "instrument_id" | "instrument_name" | "instrument_type" | "last_price"
  | "change_percent" | "status_label">;
