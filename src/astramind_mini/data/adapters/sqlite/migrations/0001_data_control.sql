CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_probe_runs (
    probe_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    probed_at TEXT NOT NULL,
    report_path TEXT NOT NULL,
    report_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_versions (
    dataset_version TEXT PRIMARY KEY,
    dataset_name TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS data_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    as_of TEXT NOT NULL,
    created_at TEXT NOT NULL,
    manifest_path TEXT NOT NULL
);
