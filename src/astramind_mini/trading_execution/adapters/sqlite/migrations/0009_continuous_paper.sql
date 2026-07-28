CREATE TABLE paper_limit_proposals (
    identity TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL,
    account_baseline_id TEXT NOT NULL,
    state TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE paper_submission_approvals (
    identity TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    authorization_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE paper_broker_commands (
    identity TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
