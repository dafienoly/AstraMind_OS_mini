"""Parquet schemas for MiniQMT reference and financial datasets."""

FINANCIAL_FACT_COLUMNS = (
    ("provider", "VARCHAR"),
    ("source_endpoint", "VARCHAR"),
    ("retrieved_at", "TIMESTAMPTZ"),
    ("available_at", "TIMESTAMPTZ"),
    ("schema_version", "VARCHAR"),
    ("source_record_hash", "VARCHAR"),
    ("instrument_id", "VARCHAR"),
    ("statement_type", "VARCHAR"),
    ("report_period", "DATE"),
    ("announced_on", "DATE"),
    ("revision_identity", "VARCHAR"),
    ("field_name", "VARCHAR"),
    ("numeric_value", "DOUBLE"),
    ("currency", "VARCHAR"),
    ("unit", "VARCHAR"),
    ("applicability", "VARCHAR"),
)

TOP_HOLDER_COLUMNS = (
    ("provider", "VARCHAR"),
    ("source_endpoint", "VARCHAR"),
    ("retrieved_at", "TIMESTAMPTZ"),
    ("available_at", "TIMESTAMPTZ"),
    ("schema_version", "VARCHAR"),
    ("source_record_hash", "VARCHAR"),
    ("instrument_id", "VARCHAR"),
    ("holder_scope", "VARCHAR"),
    ("report_period", "DATE"),
    ("announced_on", "DATE"),
    ("rank", "INTEGER"),
    ("holder_name", "VARCHAR"),
    ("holding_amount", "DOUBLE"),
    ("holding_ratio_percent", "DOUBLE"),
    ("holder_type", "VARCHAR"),
    ("revision_identity", "VARCHAR"),
)

INDEX_WEIGHT_COLUMNS = (
    ("provider", "VARCHAR"),
    ("source_endpoint", "VARCHAR"),
    ("retrieved_at", "TIMESTAMPTZ"),
    ("available_at", "TIMESTAMPTZ"),
    ("schema_version", "VARCHAR"),
    ("source_record_hash", "VARCHAR"),
    ("index_id", "VARCHAR"),
    ("instrument_id", "VARCHAR"),
    ("observed_on", "DATE"),
    ("weight_percent", "DOUBLE"),
    ("membership_semantics", "VARCHAR"),
)

SECTOR_MEMBERSHIP_COLUMNS = (
    ("provider", "VARCHAR"),
    ("source_endpoint", "VARCHAR"),
    ("retrieved_at", "TIMESTAMPTZ"),
    ("available_at", "TIMESTAMPTZ"),
    ("schema_version", "VARCHAR"),
    ("source_record_hash", "VARCHAR"),
    ("sector_name", "VARCHAR"),
    ("instrument_id", "VARCHAR"),
    ("observed_on", "DATE"),
    ("membership_semantics", "VARCHAR"),
)

INSTRUMENT_SNAPSHOT_COLUMNS = (
    ("provider", "VARCHAR"),
    ("source_endpoint", "VARCHAR"),
    ("retrieved_at", "TIMESTAMPTZ"),
    ("available_at", "TIMESTAMPTZ"),
    ("schema_version", "VARCHAR"),
    ("source_record_hash", "VARCHAR"),
    ("instrument_id", "VARCHAR"),
    ("observed_on", "DATE"),
    ("name", "VARCHAR"),
    ("exchange_id", "VARCHAR"),
    ("listed_on", "DATE"),
    ("delisted_on", "DATE"),
    ("total_shares", "DOUBLE"),
    ("float_shares", "DOUBLE"),
    ("previous_close", "DOUBLE"),
    ("upper_limit", "DOUBLE"),
    ("lower_limit", "DOUBLE"),
    ("is_trading", "BOOLEAN"),
    ("stock_status", "INTEGER"),
)

__all__ = [
    "FINANCIAL_FACT_COLUMNS",
    "INDEX_WEIGHT_COLUMNS",
    "INSTRUMENT_SNAPSHOT_COLUMNS",
    "SECTOR_MEMBERSHIP_COLUMNS",
    "TOP_HOLDER_COLUMNS",
]
