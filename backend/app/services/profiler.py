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
from app.services.error_safety import safe_profile_error

logger = logging.getLogger(__name__)

# Column type categories
NUMERIC_TYPES = {
    "int", "integer", "bigint", "smallint", "tinyint", "mediumint",
    "numeric", "decimal", "real", "money", "smallmoney",
    "double", "double precision", "float", "float4", "float8", "int2", "int4", "int8",
    "INT64", "FLOAT64", "NUMERIC", "BIGNUMERIC",  # BigQuery
    "NUMBER", "FLOAT",  # Snowflake / DuckDB
}
TIMESTAMP_TYPES = {
    "timestamp", "timestamp without time zone", "timestamp with time zone",
    "timestamptz", "datetime", "datetime2", "smalldatetime", "datetimeoffset",
    "TIMESTAMP", "DATETIME",
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
        for modifier in (" UNSIGNED", " ZEROFILL"):
            t = t.replace(modifier, "")
        if any(nt.upper() == t for nt in NUMERIC_TYPES):
            return "numeric"
        if any(tt.upper() == t for tt in TIMESTAMP_TYPES):
            return "timestamp"
        if any(dt.upper() == t for dt in DATE_TYPES):
            return "date"
        return "text"


@dataclass
class ProfileResult:
    row_count: int = 0
    freshness_seconds: float | None = None
    schema_fingerprint: str = ""
    column_metrics: dict[str, Any] = field(default_factory=dict)
    profiling_duration_ms: int = 0
    error: str | None = None


class ProfilerService:
    """
    Builds and executes a single aggregate SQL query per table.
    Column introspection result is passed in (caller caches it).
    """

    @staticmethod
    def _split_ddl_column(line: str) -> tuple[str, str] | None:
        """Split a DDL-like column line while preserving quoted identifier spaces."""
        if not line:
            return None
        opener = line[0]
        closers = {'"': '"', '`': '`', '[': ']'}
        closer = closers.get(opener)
        if closer:
            chars: list[str] = []
            i = 1
            while i < len(line):
                ch = line[i]
                if ch == closer:
                    if i + 1 < len(line) and line[i + 1] == closer:
                        chars.append(closer)
                        i += 2
                        continue
                    return "".join(chars), line[i + 1:].strip()
                chars.append(ch)
                i += 1
            return None
        parts = line.split(maxsplit=1)
        return (parts[0], parts[1]) if len(parts) == 2 else None

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
            split = self._split_ddl_column(line)
            if split:
                col_name, remainder = split
                nullable = "NOT NULL" not in line
                # Strip trailing NULL/NOT NULL to capture multi-word types
                # e.g. "character varying NULL" → "character varying"
                for suffix in ("NOT NULL", "NULL"):
                    if remainder.endswith(suffix):
                        remainder = remainder[: -len(suffix)].strip()
                        break
                data_type = remainder
                columns.append(ColumnInfo(name=col_name, data_type=data_type, is_nullable=nullable))
        return columns

    def compute_schema_fingerprint(self, columns: list[ColumnInfo]) -> str:
        """MD5 of sorted col_name:col_type pairs."""
        pairs = sorted(f"{c.name}:{c.data_type}" for c in columns)
        return hashlib.md5("|".join(pairs).encode()).hexdigest()

    @staticmethod
    def _quote_identifier(identifier: str, dialect: str = "postgres") -> str:
        """Quote a discovered identifier without treating it as SQL text."""
        if not identifier or "\x00" in identifier:
            raise ValueError("Database identifiers must be non-empty and contain no NUL bytes")
        if dialect == "mysql":
            return f"`{identifier.replace('`', '``')}`"
        if dialect == "sqlserver":
            return f"[{identifier.replace(']', ']]')}]"
        return f'"{identifier.replace(chr(34), chr(34) * 2)}"'

    def _qualified_table(self, schema: str, table: str, dialect: str = "postgres") -> str:
        return (
            f"{self._quote_identifier(schema, dialect)}."
            f"{self._quote_identifier(table, dialect)}"
        )

    def _metric_alias(self, metric: str, column: str, dialect: str = "postgres") -> str:
        return self._quote_identifier(f"{metric}_{column}", dialect)

    def build_profile_query(
        self,
        schema: str,
        table: str,
        columns: list[ColumnInfo],
        freshness_column: str | None,
        dialect: str = "postgres",
    ) -> str:
        """
        Build a single SELECT with all aggregate metrics.
        Returns (query_string, metric_keys_in_order).
        """
        if dialect not in {"postgres", "duckdb", "sqlite", "mysql", "sqlserver"}:
            raise ValueError(f"Unsupported profiling dialect: {dialect}")

        sqlite = dialect == "sqlite"
        mysql = dialect == "mysql"
        sqlserver = dialect == "sqlserver"
        parts = [
            "COUNT(*) AS _row_count",
            # Duplicate rate: what fraction of rows are duplicates of at least one other row
            # Approximated via: 1 - (COUNT(DISTINCT all_cols) / COUNT(*))
            # We approximate per-column uniqueness instead (cheaper)
        ]

        if freshness_column:
            freshness = self._quote_identifier(freshness_column, dialect)
            if sqlite:
                parts.append(
                    f"(julianday('now') - julianday(MAX({freshness}))) * 86400.0 "
                    "AS _freshness_seconds"
                )
            elif mysql:
                parts.append(
                    f"TIMESTAMPDIFF(SECOND, MAX({freshness}), CURRENT_TIMESTAMP) "
                    "AS _freshness_seconds"
                )
            elif sqlserver:
                parts.append(
                    f"DATEDIFF_BIG(SECOND, MAX({freshness}), SYSUTCDATETIME()) "
                    "AS _freshness_seconds"
                )
            else:
                parts.append(
                    f"EXTRACT(EPOCH FROM NOW() - MAX({freshness})) AS _freshness_seconds"
                )

        for col in columns:
            safe = self._quote_identifier(col.name, dialect)
            cat = col.category

            def alias(metric: str) -> str:
                return self._metric_alias(metric, col.name, dialect)

            # Null rate — all types
            if sqlite:
                parts.append(
                    f"CAST(SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END) AS REAL) "
                    f"/ NULLIF(COUNT(*), 0) AS {alias('null_rate')}"
                )
            elif mysql or sqlserver:
                parts.append(
                    f"SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END) * 1.0 "
                    f"/ NULLIF(COUNT(*), 0) AS {alias('null_rate')}"
                )
            else:
                parts.append(
                    f"SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END)::FLOAT "
                    f"/ NULLIF(COUNT(*), 0) AS {alias('null_rate')}"
                )
            # Distinct count — all types
            parts.append(f"COUNT(DISTINCT {safe}) AS {alias('distinct_count')}")
            # Uniqueness ratio — 1.0 means all values unique, lower = many duplicates
            if sqlite:
                parts.append(
                    f"CAST(COUNT(DISTINCT {safe}) AS REAL) / NULLIF(COUNT(*), 0) "
                    f"AS {alias('uniqueness_ratio')}"
                )
            elif mysql or sqlserver:
                parts.append(
                    f"COUNT(DISTINCT {safe}) * 1.0 / NULLIF(COUNT(*), 0) "
                    f"AS {alias('uniqueness_ratio')}"
                )
            else:
                parts.append(
                    f"COUNT(DISTINCT {safe})::FLOAT / NULLIF(COUNT(*), 0) "
                    f"AS {alias('uniqueness_ratio')}"
                )

            if cat == "numeric":
                parts += [
                    f"MIN({safe}) AS {alias('min')}",
                    f"MAX({safe}) AS {alias('max')}",
                ]
                if sqlite:
                    parts += [
                        f"AVG(CAST({safe} AS REAL)) AS {alias('mean')}",
                        f"CAST(SUM(CASE WHEN {safe} = 0 THEN 1 ELSE 0 END) AS REAL) "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('zero_rate')}",
                        f"CAST(SUM(CASE WHEN {safe} < 0 THEN 1 ELSE 0 END) AS REAL) "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('negative_rate')}",
                    ]
                elif mysql:
                    parts += [
                        f"AVG({safe}) AS {alias('mean')}",
                        f"STDDEV_POP({safe}) AS {alias('stddev')}",
                        f"SUM(CASE WHEN {safe} = 0 THEN 1 ELSE 0 END) * 1.0 "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('zero_rate')}",
                        f"SUM(CASE WHEN {safe} < 0 THEN 1 ELSE 0 END) * 1.0 "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('negative_rate')}",
                    ]
                elif sqlserver:
                    parts += [
                        f"AVG(CAST({safe} AS FLOAT)) AS {alias('mean')}",
                        f"STDEVP(CAST({safe} AS FLOAT)) AS {alias('stddev')}",
                        f"SUM(CASE WHEN {safe} = 0 THEN 1 ELSE 0 END) * 1.0 "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('zero_rate')}",
                        f"SUM(CASE WHEN {safe} < 0 THEN 1 ELSE 0 END) * 1.0 "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('negative_rate')}",
                    ]
                else:
                    parts += [
                        f"AVG({safe}::FLOAT) AS {alias('mean')}",
                        f"STDDEV({safe}::FLOAT) AS {alias('stddev')}",
                        f"PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {safe}) AS {alias('p25')}",
                        f"PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY {safe}) AS {alias('p50')}",
                        f"PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {safe}) AS {alias('p75')}",
                        f"PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY {safe}) AS {alias('p95')}",
                        f"SUM(CASE WHEN {safe} = 0 THEN 1 ELSE 0 END)::FLOAT "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('zero_rate')}",
                        f"SUM(CASE WHEN {safe} < 0 THEN 1 ELSE 0 END)::FLOAT "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('negative_rate')}",
                    ]
            elif cat in ("timestamp", "date"):
                parts += [
                    f"MIN({safe}) AS {alias('min')}",
                    f"MAX({safe}) AS {alias('max')}",
                ]
                if sqlite:
                    parts.append(
                        f"(julianday(MAX({safe})) - julianday(MIN({safe}))) * 86400.0 "
                        f"AS {alias('range_seconds')}"
                    )
                elif mysql:
                    parts.append(
                        f"TIMESTAMPDIFF(SECOND, MIN({safe}), MAX({safe})) "
                        f"AS {alias('range_seconds')}"
                    )
                elif sqlserver:
                    parts.append(
                        f"DATEDIFF_BIG(SECOND, MIN({safe}), MAX({safe})) "
                        f"AS {alias('range_seconds')}"
                    )
                else:
                    parts.append(
                        f"EXTRACT(EPOCH FROM MAX({safe}) - MIN({safe})) "
                        f"AS {alias('range_seconds')}"
                    )
            else:  # text / other
                if sqlite:
                    text_value = f"CAST({safe} AS TEXT)"
                elif mysql:
                    text_value = f"CAST({safe} AS CHAR)"
                elif sqlserver:
                    text_value = f"CAST({safe} AS NVARCHAR(MAX))"
                else:
                    text_value = f"{safe}::TEXT"
                length_value = (
                    f"LEN({text_value} + N'#') - 1"
                    if sqlserver
                    else f"{'CHAR_LENGTH' if mysql else 'LENGTH'}({text_value})"
                )
                parts += [
                    f"MIN({length_value}) AS {alias('min_len')}",
                    f"MAX({length_value}) AS {alias('max_len')}",
                    f"AVG(CAST({length_value} AS FLOAT)) AS {alias('avg_len')}"
                    if sqlserver
                    else f"AVG({length_value}) AS {alias('avg_len')}",
                ]
                if sqlite:
                    parts.append(
                        f"CAST(SUM(CASE WHEN {text_value} = '' THEN 1 ELSE 0 END) AS REAL) "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('empty_rate')}"
                    )
                elif mysql or sqlserver:
                    parts.append(
                        f"SUM(CASE WHEN {text_value} = '' THEN 1 ELSE 0 END) * 1.0 "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('empty_rate')}"
                    )
                else:
                    parts.append(
                        f"SUM(CASE WHEN {text_value} = '' THEN 1 ELSE 0 END)::FLOAT "
                        f"/ NULLIF(COUNT(*) - SUM(CASE WHEN {safe} IS NULL THEN 1 ELSE 0 END), 0) "
                        f"AS {alias('empty_rate')}"
                    )

        select_clause = ",\n       ".join(parts)
        qualified_table = self._qualified_table(schema, table, dialect)
        return f"SELECT {select_clause}\nFROM {qualified_table}"

    async def get_top_values(
        self,
        connector: BaseConnector,
        schema: str,
        table: str,
        columns: list[ColumnInfo],
        limit: int = 10,
    ) -> dict[str, list[dict]]:
        """Fetch top N most frequent values for categorical columns (max 5 cols to avoid query bloat)."""
        if limit < 1 or limit > 100:
            raise ValueError("Top-value limit must be between 1 and 100")

        text_cols = [c for c in columns if c.category == "text"][:5]
        top_values: dict[str, list[dict]] = {}
        for col in text_cols:
            try:
                dialect = getattr(connector, "profile_dialect", "postgres")
                safe_col = self._quote_identifier(col.name, dialect)
                text_cast = "CHAR" if dialect == "mysql" else "TEXT"
                q = (
                    f"SELECT CAST({safe_col} AS {text_cast}) AS val, COUNT(*) AS cnt "
                    f"FROM {self._qualified_table(schema, table, dialect)} "
                    f"WHERE {safe_col} IS NOT NULL "
                    f"GROUP BY {safe_col} ORDER BY cnt DESC LIMIT {limit}"
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
            dialect = getattr(connector, "profile_dialect", None)
            if dialect is None:
                return ProfileResult(
                    error=(
                        f"{type(connector).__name__} supports connection/discovery but "
                        "does not yet support automated profiling"
                    )
                )
            columns = await self._get_columns_raw(connector, schema, table)
            if not columns:
                return ProfileResult(error="Could not introspect columns")

            fingerprint = self.compute_schema_fingerprint(columns)

            # One aggregate query is the correctness and cost contract. Sampling must
            # not be reintroduced until a connector can provide a non-scanning row
            # estimate and sampled metrics carry explicit provenance.
            query = self.build_profile_query(
                schema,
                table,
                columns,
                freshness_column,
                dialect=dialect,
            )

            logger.info("Profiling %s.%s — query built, executing", schema, table)
            raw = await connector.execute_profile_query(query)

            duration_ms = int((time.monotonic() - start) * 1000)
            result = self.parse_results(raw, columns, freshness_column, fingerprint, duration_ms)

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
            logger.error(
                "Profiling failed for %s.%s: %s",
                schema,
                table,
                type(e).__name__,
            )
            return ProfileResult(
                error=safe_profile_error(e),
                profiling_duration_ms=duration_ms,
            )
