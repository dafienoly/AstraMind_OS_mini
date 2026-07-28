"""DuckDB query for exact-snapshot tactical candidates."""

CANDIDATE_SQL = """
WITH tradability AS (
  SELECT *,
         row_number() OVER (
           PARTITION BY instrument_id ORDER BY trade_date
         ) AS listed_sessions
  FROM read_parquet(?)
  WHERE trade_date <= ?
), market AS (
  SELECT d.instrument_id, d.trade_date, d.open, d.close,
         d.amount_thousand_cny * 1000 AS amount_cny,
         a.research_close_index, t.risk_status, t.buy_state, t.sell_state,
         t.listed_sessions,
         median(d.amount_thousand_cny * 1000) OVER (
           PARTITION BY d.instrument_id ORDER BY d.trade_date
           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
         ) AS median_amount_20,
         max(a.research_close_index) OVER (
           PARTITION BY d.instrument_id ORDER BY d.trade_date
           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
         ) AS prior_high_20,
         lag(a.research_close_index, 1) OVER (
           PARTITION BY d.instrument_id ORDER BY d.trade_date
         ) AS previous_index,
         lag(a.research_close_index, 5) OVER (
           PARTITION BY d.instrument_id ORDER BY d.trade_date
         ) AS index_5_sessions_ago
  FROM read_parquet(?) d
  JOIN read_parquet(?) a USING (instrument_id, trade_date)
  JOIN tradability t USING (instrument_id, trade_date)
  WHERE d.trade_date >= CAST(? AS DATE) - INTERVAL 60 DAYS
), sessions AS (
  SELECT trade_date, row_number() OVER (ORDER BY trade_date) AS session_number
  FROM (SELECT DISTINCT trade_date FROM market)
), features AS (
  SELECT m.*, s.session_number, coalesce(e.event_count, 0) AS event_count,
         e.net_rate, e.institutional_net,
         m.research_close_index / nullif(m.prior_high_20, 0) - 1 AS breakout,
         m.research_close_index / nullif(m.index_5_sessions_ago, 0) - 1 AS return_5,
         m.research_close_index / nullif(m.previous_index, 0) - 1 AS return_1,
         m.amount_cny / nullif(m.median_amount_20, 0) AS amount_ratio
  FROM market m JOIN sessions s USING (trade_date)
  LEFT JOIN event_context e USING (instrument_id, trade_date)
), signals AS (
  SELECT *,
    CASE
      WHEN ? = 'event_attention'
        THEN abs(coalesce(net_rate, 0)) + least(abs(coalesce(institutional_net, 0)) / 10000000, 10)
      WHEN ? = 'momentum_breakout' THEN breakout * 100 + least(amount_ratio, 3)
      ELSE abs(return_5) * 100 + return_1 * 20 + greatest(0, 1.5 - amount_ratio)
    END AS score
  FROM features
  WHERE listed_sessions >= 60 AND risk_status = 'normal'
    AND buy_state = 'tradable' AND sell_state = 'tradable'
    AND (median_amount_20 >= 20000000 OR (? = 'event_attention' AND event_count > 0))
    AND CASE
      WHEN ? = 'event_attention' THEN event_count > 0
      WHEN ? = 'momentum_breakout' THEN breakout > 0 AND amount_ratio >= 1.1
      ELSE return_5 <= -0.08 AND return_1 > 0 AND amount_ratio <= 1.5
    END
    AND trade_date BETWEEN ? AND ?
), planned AS (
  SELECT q.*, entry.trade_date AS entry_date, entry.open AS entry_open,
         entry.amount_cny AS entry_amount, entry.buy_state AS entry_buy_state,
         target.trade_date AS target_exit_date
  FROM signals q
  LEFT JOIN sessions next_session
    ON next_session.session_number = q.session_number + 1
  LEFT JOIN market entry
    ON entry.instrument_id = q.instrument_id
   AND entry.trade_date = next_session.trade_date
  LEFT JOIN sessions target
    ON target.session_number = q.session_number + ?
), exits AS (
  SELECT p.*, x.trade_date AS exit_date, x.open AS exit_open
  FROM planned p
  LEFT JOIN LATERAL (
    SELECT m.trade_date, m.open
    FROM market m
    WHERE m.instrument_id = p.instrument_id
      AND m.trade_date >= p.target_exit_date
      AND m.trade_date <= ?
      AND m.sell_state = 'tradable'
    ORDER BY m.trade_date
    LIMIT 1
  ) x ON true
)
SELECT instrument_id, trade_date, score, event_count, net_rate, institutional_net,
       entry_date, entry_open, entry_amount, entry_buy_state,
       target_exit_date, exit_date, exit_open
FROM exits
WHERE entry_date IS NOT NULL
ORDER BY entry_date, score DESC, instrument_id
"""

CURRENT_SIGNAL_SQL = """
WITH tradability AS (
  SELECT *,
         row_number() OVER (
           PARTITION BY instrument_id ORDER BY trade_date
         ) AS listed_sessions
  FROM read_parquet(?)
  WHERE trade_date <= ?
), market AS (
  SELECT d.instrument_id, d.trade_date, d.close,
         d.amount_thousand_cny * 1000 AS amount_cny,
         a.research_close_index, t.risk_status, t.buy_state, t.sell_state,
         t.listed_sessions,
         median(d.amount_thousand_cny * 1000) OVER (
           PARTITION BY d.instrument_id ORDER BY d.trade_date
           ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
         ) AS median_amount_20,
         lag(a.research_close_index, 1) OVER (
           PARTITION BY d.instrument_id ORDER BY d.trade_date
         ) AS previous_index,
         lag(a.research_close_index, 5) OVER (
           PARTITION BY d.instrument_id ORDER BY d.trade_date
         ) AS index_5_sessions_ago
  FROM read_parquet(?) d
  JOIN read_parquet(?) a USING (instrument_id, trade_date)
  JOIN tradability t USING (instrument_id, trade_date)
  WHERE d.trade_date >= CAST(? AS DATE) - INTERVAL 60 DAYS
), features AS (
  SELECT *,
         research_close_index / nullif(index_5_sessions_ago, 0) - 1 AS return_5,
         research_close_index / nullif(previous_index, 0) - 1 AS return_1,
         amount_cny / nullif(median_amount_20, 0) AS amount_ratio
  FROM market
), signals AS (
  SELECT *,
         abs(return_5) * 100 + return_1 * 20
           + greatest(0, 1.5 - amount_ratio) AS score
  FROM features
  WHERE trade_date = ?
    AND listed_sessions >= 60 AND risk_status = 'normal'
    AND buy_state = 'tradable' AND sell_state = 'tradable'
    AND median_amount_20 >= 20000000
    AND return_5 <= -0.08 AND return_1 > 0 AND amount_ratio <= 1.5
)
SELECT instrument_id, trade_date, score, close, return_5, return_1, amount_ratio
FROM signals
ORDER BY score DESC, instrument_id
"""

__all__ = ["CANDIDATE_SQL", "CURRENT_SIGNAL_SQL"]
