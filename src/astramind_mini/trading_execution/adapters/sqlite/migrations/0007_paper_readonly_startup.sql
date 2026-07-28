CREATE TABLE paper_mode_locks (
    identity TEXT PRIMARY KEY,
    account_snapshot_id TEXT,
    state TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE paper_callback_handshakes (
    identity TEXT PRIMARY KEY,
    account_snapshot_id TEXT NOT NULL,
    state TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE paper_account_baselines (
    identity TEXT PRIMARY KEY,
    account_snapshot_id TEXT NOT NULL,
    state TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
