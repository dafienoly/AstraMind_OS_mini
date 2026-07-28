CREATE TABLE account_snapshot_publications (
    identity TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    state TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE reconciliation_publications (
    identity TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    state TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
