CREATE TABLE continuous_shadow_checkpoints (
    identity TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    status TEXT NOT NULL,
    state_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_continuous_shadow_checkpoints_cycle
ON continuous_shadow_checkpoints(cycle_id, trading_date, created_at);

CREATE TABLE continuous_shadow_results (
    identity TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
