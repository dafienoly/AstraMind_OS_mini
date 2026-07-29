CREATE TABLE IF NOT EXISTS daily_pipeline_checkpoint_history (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    superseded_at TEXT NOT NULL,
    recovery_reason TEXT NOT NULL,
    UNIQUE(run_id, step_id, content_hash)
);
