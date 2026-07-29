"""DuckDB schemas for ETF foundation datasets."""

SOURCE_COLUMNS = (
    ("provider", "VARCHAR"),
    ("source_endpoint", "VARCHAR"),
    ("retrieved_at", "TIMESTAMPTZ"),
    ("available_at", "TIMESTAMPTZ"),
    ("schema_version", "VARCHAR"),
    ("source_record_hash", "VARCHAR"),
)

ETF_MASTER_COLUMNS = (
    *SOURCE_COLUMNS,
    ("instrument_id", "VARCHAR"),
    ("name", "VARCHAR"),
    ("fund_type", "VARCHAR"),
    ("invest_type", "VARCHAR"),
    ("benchmark", "VARCHAR"),
    ("exchange", "VARCHAR"),
    ("found_date", "DATE"),
    ("list_date", "DATE"),
    ("delist_date", "DATE"),
    ("list_status", "VARCHAR"),
)

ETF_DAILY_COLUMNS = (
    *SOURCE_COLUMNS,
    ("instrument_id", "VARCHAR"),
    ("trade_date", "DATE"),
    ("open", "DOUBLE"),
    ("high", "DOUBLE"),
    ("low", "DOUBLE"),
    ("close", "DOUBLE"),
    ("previous_close", "DOUBLE"),
    ("change", "DOUBLE"),
    ("percent_change", "DOUBLE"),
    ("volume_lots", "DOUBLE"),
    ("amount_cny", "DOUBLE"),
)

ETF_SHARE_COLUMNS = (
    *SOURCE_COLUMNS,
    ("instrument_id", "VARCHAR"),
    ("trade_date", "DATE"),
    ("fund_share", "DOUBLE"),
)

ETF_MAPPING_COLUMNS = (
    *SOURCE_COLUMNS,
    ("taxonomy", "VARCHAR"),
    ("taxonomy_version", "VARCHAR"),
    ("industry_code", "VARCHAR"),
    ("industry_name", "VARCHAR"),
    ("etf_code", "VARCHAR"),
    ("semantic_tier", "VARCHAR"),
    ("tracked_index", "VARCHAR"),
    ("eligible_for_foundation", "BOOLEAN"),
    ("effective_from", "DATE"),
    ("effective_to", "DATE"),
    ("mapping_version", "VARCHAR"),
    ("evidence_source", "VARCHAR"),
)

__all__ = [
    "ETF_DAILY_COLUMNS",
    "ETF_MAPPING_COLUMNS",
    "ETF_MASTER_COLUMNS",
    "ETF_SHARE_COLUMNS",
]
