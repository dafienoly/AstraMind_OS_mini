CREATE TABLE promotion_decisions (
    decision_id TEXT PRIMARY KEY,
    strategy_version_id TEXT NOT NULL,
    evidence_bundle_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    sleeve TEXT NOT NULL CHECK (sleeve = 'tactical'),
    outcome TEXT NOT NULL CHECK (outcome IN ('promoted', 'rejected')),
    decided_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX promotion_decisions_sleeve_time
ON promotion_decisions(sleeve, decided_at);
