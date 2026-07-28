CREATE TABLE paper_canary_authorizations (
    identity TEXT PRIMARY KEY,
    standing_mandate_id TEXT NOT NULL,
    portfolio_target_id TEXT NOT NULL,
    account_baseline_id TEXT NOT NULL,
    state TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
