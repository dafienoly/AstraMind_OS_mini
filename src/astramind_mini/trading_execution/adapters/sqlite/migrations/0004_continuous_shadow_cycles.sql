CREATE TABLE continuous_shadow_cycles (
    identity TEXT PRIMARY KEY,
    order_plan_id TEXT NOT NULL,
    status TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
