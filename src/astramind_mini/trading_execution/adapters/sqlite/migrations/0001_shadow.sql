CREATE TABLE shadow_events (
    execution_event_id TEXT PRIMARY KEY,
    order_plan_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(order_plan_id, sequence)
);
