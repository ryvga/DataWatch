"""
ProfilerService: single-query table profiler.

Design principle: ONE SQL aggregate query per table run.
Never pulls rows to the application layer.
"""
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

# Column type categories
NUMERIC_TYPES = {
    "integer", "bigint", "smallint", "numeric", "decimal", "real",
    "double precision", "float", "float4", "float8", "int2", "int4", "int8",
    "INT64", "FLOAT64", "NUMERIC", "BIGNUMERIC",  # BigQuery
    "NUMBER", "FLOAT",  # Snowflake / DuckDB
}
TIMESTAMP_TYPES = {
    "timestamp", "timestamp without time zone", "timestamp with time zone",
    "timestamptz", "datetime", "TIMESTAMP", "DATETIME",
}
DATE_TYPES = {"date", "DATE"}
TEXT_TYPES = {
    "text", "varchar", "character varying", "char", "bpchar", "uuid",
    "STRING", "VARCHAR", "BYTES",
}


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool = True

    @property
    def category(self) -> str:
        t = self.data_type.upper().split("(")[0].strip()
        if any(nt.upper() == t for nt in NUMERIC_TYPES):
            return "numeric"
        if any(tt.upper() == t for tt in TIMESTAMP_TYPES):
            return "timestamp"
        if any(dt.upper() == t for dt in DATE_TYPES):
            return "date"
        return "text"


LARGE_TABLE_THRESHOLD = 5_000_000   # rows — trigger sampling
SAMPLE_TARGET_ROWS = 1_000_000       # rows to sample for large tables


@dataclass
class ProfileResult:
    row_count: int = 0
    freshness_seconds: float | None = None
    schema_fingerprint: str = ""
    column_metrics: dict[str, Any] = field(default_factory=dict)
    profiling_duration_ms: int = 0
    error: str | None = None
    sampled: bool = False
    sample_pct: float | None = None


class ProfilerService:
    """
    Builds and executes a single aggregate SQL query per table.
    Column introspection result is passed in (caller caches it).
    """

    async def get_columns(
        self, connector: BaseConnector, schema: str, table: str
    ) -> list[ColumnInfo]:
        """Fetch column metadata from information_schema."""
        query = f"""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = '{schema}' AND table_name = '{table}'
            ORDER BY ordinal_position
        """
        try:
            rows = await connector.execute_profile_query(query)
            # execute_profile_query returns a single dict — we need multiple rows
            # Use a different approach: wrap in a subquery that returns JSON
            return await self._get_columns_raw(connector, schema, table)
        except Exception:
            return await self._get_columns_raw(connector, schema, table)

    async def _get_columns_raw(
        self, connector: BaseConnector, schema: str, table: str
    ) -> list[ColumnInfo]:
        """Get columns via DDL parsing fallback."""
        ddl = await connector.get_table_ddl(schema, table)
        columns = []
        for line in ddl.split("\n"):
            line = line.strip().rstrip(",")
            if line.startswith("CREATE TABLE") or line in ("{", "}", ");", "("):
                continue
            parts = line.split()
            if len(parts) >= 2:
                col_name = parts[0]
                data_type = parts[1]
                nullable = "NOT NULL" not in line
                columns.append(ColumnInfo(name=col_name, data_type=data_type, is_nullable=nullable))
        return columns

    def compute_schema_fingerprint(self, columns: list[ColumnInfo]) -> str:
        """MD5 of sorted col_name:col_type pairs."""
        pairs = sorted(f"{c.name}:{c.data_type}" for c in columns)
        return hashlib.md5("|".join(pairs).encode()).hexdigest()

    def build_profile_query(
        self,
        schema: str,
        table: str,
        columns: list[ColumnInfo],
        freshness_column: str | None,
        sample_pct: float | None = None,
    ) -> str:
        """
        Build a single SELECT with all aggregate metrics.
        Returns (query_string, metric_keys_in_order).
        """
        parts = [
            "COUNT(*) AS _row_count",
            # Duplicate rate: what fraction of rows are duplicates of at least one other row
            # Approximated via: 1 - (COUNT(DISTINCT all_cols) / COUNT(*))
            # We approximate per-column uniqueness instead (cheaper)
        ]

        if freshness_column:
            parts.append(
                f"EXTRACT(EPOCH FROM NOW() - MAX({freshness_column})) AS _freshness_seconds"
            )

        for col in columns:
            safe = col.name
            cat = col.category

            # Null rate — all types
            parts.append(
                f"SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END)::FLOAT "
                f"/ NULLIF(COUNT(*), 0) AS null_rate_{safe}"
            )
            # Distinct count — all types
            parts.append(f"COUNT(DISTINCT {safe}) AS distinct_count_{safe}")
            # Uniqueness ratio — 1.0 means all values unique, lower = many duplicates
            parts.append(
                f"COUNT(DISTINCT {safe})::FLOAT / NULLIF(COUNT(*), 0) AS uniqueness_ratio_{safe}"
            )

            if cat == "numeric":
                parts += [
                    f"MIN({safe}) AS min_{safe}",
                    f"MAX({safe}) AS max_{safe}",
                    f"AVG({safe}::FLOAT) AS mean_{safe}",
                    f"STDDEV({safe}::FLOAT) AS stddev_{safe}",
                    f"PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {safe}) AS p25_{safe}",
                    f"PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {safe}) AS p50_{safe}",
                    f"PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {safe}) AS p75_{safe}",
                    f"PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY {safe}) AS p95_{safe}",
                    f"SUM(CASE WHEN {safe} = 0 THEN 1 ELSE 0 END)::FLOAT "
                    f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) AS zero_rate_{safe}",
                    f"SUM(CASE WHEN {safe} < 0 THEN 1 ELSE 0 END)::FLOAT "
                    f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) AS negative_rate_{safe}",
                ]
            elif cat in ("timestamp", "date"):
                parts += [
                    f"MIN({safe}) AS min_{safe}",
                    f"MAX({safe}) AS max_{safe}",
                    f"EXTRACT(EPOCH FROM MAX({safe}) - MIN({safe})) AS range_seconds_{safe}",
                ]
            else:  # text / other
                parts += [
                    f"MIN(LENGTH({safe}::TEXT)) AS min_len_{safe}",
                    f"MAX(LENGTH({safe}::TEXT)) AS max_len_{safe}",
                    f"AVG(LENGTH({safe}::TEXT)) AS avg_len_{safe}",
                    f"SUM(CASE WHEN {safe}::TEXT = '' THEN 1 ELSE 0 END)::FLOAT "
                    f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) AS empty_rate_{safe}",
                ]

        select_clause = ",\n       ".join(parts)
        if sample_pct is not None and sample_pct < 100:
            from_clause = f"{schema}.{table} TABLESAMPLE SYSTEM({sample_pct:.2f})"
        else:
            from_clause = f"{schema}.{table}"
        return f"SELECT {select_clause}\nFROM {from_clause}"

    async def get_top_values(
        self,
        connector: BaseConnector,
        schema: str,
        table: str,
        columns: list[ColumnInfo],
        limit: int = 10,
    ) -> dict[str, list[dict]]:
        """Fetch top N most frequent values for categorical columns (max 5 cols to avoid query bloat)."""
        text_cols = [c for c in columns if c.category == "text"][:5]
        top_values: dict[str, list[dict]] = {}
        for col in text_cols:
            try:
                q = (
                    f"SELECT {col.name}::TEXT AS val, COUNT(*) AS cnt "
                    f"FROM {schema}.{table} "
                    f"WHERE {col.name} IS NOT NULL "
                    f"GROUP BY {col.name} ORDER BY cnt DESC LIMIT {limit}"
                )
                # execute_profile_query only returns one row — use raw query method if available
                if hasattr(connector, "execute_query_many"):
                    rows = await connector.execute_query_many(q)
                    top_values[col.name] = [{"value": r["val"], "count": r["cnt"]} for r in rows]
            except Exception:
                pass
        return top_values

    def parse_results(
        self,
        raw: dict,
        columns: list[ColumnInfo],
        freshness_column: str | None,
        schema_fingerprint: str,
        duration_ms: int,
    ) -> ProfileResult:
        result = ProfileResult(
            row_count=int(raw.get("_row_count", 0) or 0),
            schema_fingerprint=schema_fingerprint,
            profiling_duration_ms=duration_ms,
        )

        if freshness_column and "_freshness_seconds" in raw:
            val = raw["_freshness_seconds"]
            result.freshness_seconds = float(val) if val is not None else None

        col_metrics: dict[str, dict] = {}
        for col in columns:
            metrics: dict[str, Any] = {}
            for key, val in raw.items():
                suffix = f"_{col.name}"
                if key.endswith(suffix):
                    metric_name = key[: -len(suffix)]
                    if isinstance(val, (int, float, Decimal)):
                        metrics[metric_name] = float(val)
                    elif isinstance(val, datetime):
                        metrics[metric_name] = val.isoformat()
                    elif isinstance(val, date):
                        metrics[metric_name] = val.isoformat()
                    else:
                        metrics[metric_name] = val
            # Cardinality ratio: distinct / non-null
            if "distinct_count" in metrics and result.row_count > 0:
                null_count = (metrics.get("null_rate", 0) or 0) * result.row_count
                non_null = result.row_count - null_count
                metrics["cardinality_ratio"] = (
                    float(metrics["distinct_count"]) / non_null if non_null > 0 else 0.0
                )
            col_metrics[col.name] = metrics

        result.column_metrics = col_metrics
        return result

    async def profile(
        self,
        connector: BaseConnector,
        schema: str,
        table: str,
        freshness_column: str | None = None,
    ) -> ProfileResult:
        start = time.monotonic()
        try:
            columns = await self._get_columns_raw(connector, schema, table)
            if not columns:
                return ProfileResult(error="Could not introspect columns")

            fingerprint = self.compute_schema_fingerprint(columns)

            # Quick estimated row count to decide sampling
            estimated_rows: int | None = None
            try:
                count_raw = await connector.execute_profile_query(
                    f"SELECT COUNT(*) AS _n FROM {schema}.{table}"
                )
                estimated_rows = int(count_raw.get("_n", 0) or 0)
            except Exception:
                pass  # count failed — proceed without sampling

            # Build profile query (with optional sampling for large tables)
            sample_pct: float | None = None
            if estimated_rows and estimated_rows > LARGE_TABLE_THRESHOLD:
                sample_pct = min(100.0, SAMPLE_TARGET_ROWS / estimated_rows * 100)
                logger.warning(
                    "Large table %s.%s (%dM rows): sampling %.1f%%",
                    schema, table, estimated_rows // 1_000_000, sample_pct,
                )
                query = self.build_profile_query(
                    schema, table, columns, freshness_column, sample_pct=sample_pct
                )
            else:
                query = self.build_profile_query(schema, table, columns, freshness_column)

            logger.info("Profiling %s.%s — query built, executing", schema, table)
            raw = await connector.execute_profile_query(query)

            duration_ms = int((time.monotonic() - start) * 1000)
            result = self.parse_results(raw, columns, freshness_column, fingerprint, duration_ms)
            if sample_pct is not None:
                result.sampled = True
                result.sample_pct = round(sample_pct, 2)

            logger.info(
                "Profile complete",
                extra={
                    "schema": schema, "table": table,
                    "row_count": result.row_count,
                    "duration_ms": duration_ms,
                },
            )
            return result

        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error("Profiling failed for %s.%s: %s", schema, table, e)
            return ProfileResult(
                error=str(e),
                profiling_duration_ms=duration_ms,
            )
