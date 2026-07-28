CREATE TABLE paper_preflight_decisions (
    identity TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    state TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE paper_convergence_reports (
    identity TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    state TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
