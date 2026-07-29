"""DuckDB schemas for immutable ETF model-evidence datasets."""

SOURCE_COLUMNS = (
    ("provider", "VARCHAR"),
    ("source_endpoint", "VARCHAR"),
    ("retrieved_at", "TIMESTAMPTZ"),
    ("available_at", "TIMESTAMPTZ"),
    ("schema_version", "VARCHAR"),
    ("source_record_hash", "VARCHAR"),
)

ETF_OFFICIAL_BENCHMARK_COLUMNS = (
    *SOURCE_COLUMNS,
    ("instrument_id", "VARCHAR"),
    ("benchmark_code", "VARCHAR"),
    ("benchmark_name", "VARCHAR"),
    ("effective_from", "DATE"),
    ("historical_availability_known", "BOOLEAN"),
    ("evidence_kind", "VARCHAR"),
)

ETF_NAV_COLUMNS = (
    *SOURCE_COLUMNS,
    ("instrument_id", "VARCHAR"),
    ("nav_date", "DATE"),
    ("announced_on", "DATE"),
    ("unit_nav", "DOUBLE"),
    ("accumulated_nav", "DOUBLE"),
    ("adjusted_nav", "DOUBLE"),
)

OFFICIAL_INDEX_DAILY_COLUMNS = (
    *SOURCE_COLUMNS,
    ("index_code", "VARCHAR"),
    ("trade_date", "DATE"),
    ("open", "DOUBLE"),
    ("high", "DOUBLE"),
    ("low", "DOUBLE"),
    ("close", "DOUBLE"),
    ("previous_close", "DOUBLE"),
    ("change", "DOUBLE"),
    ("percent_change", "DOUBLE"),
    ("volume", "DOUBLE"),
    ("amount", "DOUBLE"),
)

__all__ = [
    "ETF_NAV_COLUMNS",
    "ETF_OFFICIAL_BENCHMARK_COLUMNS",
    "OFFICIAL_INDEX_DAILY_COLUMNS",
]
