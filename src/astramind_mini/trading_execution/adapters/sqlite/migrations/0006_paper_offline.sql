CREATE TABLE paper_order_intents (
    identity TEXT PRIMARY KEY,
    order_plan_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE paper_order_observations (
    identity TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    broker_sequence INTEGER,
    received_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (intent_id) REFERENCES paper_order_intents(identity)
);

CREATE INDEX paper_order_observations_intent
ON paper_order_observations(intent_id, received_at, identity);

CREATE TABLE paper_order_projections (
    identity TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL,
    evidence_count INTEGER NOT NULL,
    state TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (intent_id) REFERENCES paper_order_intents(identity)
);

CREATE INDEX paper_order_projections_latest
ON paper_order_projections(intent_id, evidence_count DESC, updated_at DESC);
