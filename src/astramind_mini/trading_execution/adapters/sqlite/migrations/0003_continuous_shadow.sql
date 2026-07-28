CREATE TABLE reconciliation_dispositions (
    identity TEXT PRIMARY KEY,
    reconciliation_report_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE continuous_shadow_states (
    identity TEXT PRIMARY KEY,
    disposition_id TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE continuous_shadow_order_plans (
    identity TEXT PRIMARY KEY,
    state_id TEXT NOT NULL,
    portfolio_target_id TEXT NOT NULL,
    status TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
