"""Security boundary for transitional custom SQL monitors.

Legacy SQL is intentionally narrower than a general query console. Definitions must
be a single read-only SELECT scoped to the monitored asset, and execution must return
exactly one non-negative integer scalar. The typed monitor DSL will eventually replace
this escape hatch.
"""
from __future__ import annotations

import asyncio
import math
from numbers import Number

from sqlglot import exp, parse
from sqlglot.errors import ParseError

MAX_SQL_LENGTH = 32_768
DEFAULT_TIMEOUT_SECONDS = 30
MAX_VIOLATION_COUNT = 2**63 - 1

_SEVERITIES = {"P1", "P2", "P3"}
_DIALECTS = {
    "postgres": "postgres",
    "redshift": "redshift",
    "duckdb": "duckdb",
    "sqlite": "sqlite",
    "mysql": "mysql",
    "clickhouse": "clickhouse",
    "bigquery": "bigquery",
    "databricks": "databricks",
    "trino": "trino",
    "sqlserver": "tsql",
}

# SELECT can invoke functions with file, network, extension, locking, or session side
# effects. Database read-only mode is the primary boundary; this list removes common
# dangerous primitives before a query reaches the database.
_BLOCKED_FUNCTIONS = {
    "dblink", "dblink_connect", "dblink_connect_u", "dblink_exec", "glob",
    "http_get", "http_post", "install_extension", "load_extension", "lo_export",
    "lo_import", "mysql_scan", "nextval", "parquet_scan", "pg_advisory_lock",
    "pg_advisory_lock_shared", "pg_cancel_backend", "pg_logdir_ls", "pg_ls_dir",
    "pg_read_binary_file", "pg_read_file", "pg_sleep", "pg_stat_file",
    "pg_terminate_backend", "postgres_scan", "read_blob", "read_csv",
    "read_csv_auto", "read_json", "read_json_auto", "read_ndjson",
    "read_parquet", "set_config", "setval", "shell", "sqlite_scan", "system",
}


class LegacySqlPolicyError(ValueError):
    """The monitor definition violates the legacy SQL policy."""


class LegacySqlResultError(ValueError):
    """The query result is not the required violation-count scalar."""


def _function_name(function: exp.Func) -> str:
    if isinstance(function, exp.Anonymous):
        return function.name.lower()
    return function.sql_name().lower()


def _cte_names(statement: exp.Expression) -> set[str]:
    return {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }


def validate_legacy_sql(
    sql: str,
    severity: str,
    *,
    source_type: str,
    target_schema: str,
    target_table: str,
) -> str:
    """Return stripped SQL after AST, function, and single-asset validation."""
    query = sql.strip()
    if severity not in _SEVERITIES:
        raise LegacySqlPolicyError("Severity must be P1, P2, or P3")
    if not query:
        raise LegacySqlPolicyError("SQL must not be empty")
    if len(query.encode("utf-8")) > MAX_SQL_LENGTH:
        raise LegacySqlPolicyError(f"SQL must not exceed {MAX_SQL_LENGTH} bytes")

    dialect = _DIALECTS.get(source_type.lower())
    if not dialect:
        raise LegacySqlPolicyError(
            f"Legacy SQL monitors are not supported for {source_type}"
        )

    try:
        statements = parse(query, read=dialect)
    except ParseError as exc:
        raise LegacySqlPolicyError(f"SQL could not be parsed as {dialect}") from exc

    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise LegacySqlPolicyError("SQL must contain exactly one SELECT statement")

    statement = statements[0]
    prohibited_types = tuple(
        expression_type
        for name in (
            "Alter", "Command", "Copy", "Create", "Delete", "Drop", "Grant",
            "Insert", "Into", "Lock", "Merge", "Revoke", "Transaction",
            "TruncateTable", "Update", "Use",
        )
        if (expression_type := getattr(exp, name, None)) is not None
    )
    if prohibited_types and any(statement.find_all(*prohibited_types)):
        raise LegacySqlPolicyError("SQL contains a prohibited write or lock operation")

    blocked_functions = sorted(
        {
            name
            for function in statement.find_all(exp.Func)
            if (name := _function_name(function)) in _BLOCKED_FUNCTIONS
        }
    )
    if blocked_functions:
        raise LegacySqlPolicyError(
            f"SQL contains prohibited function: {blocked_functions[0]}"
        )

    ctes = _cte_names(statement)
    base_tables = [
        table
        for table in statement.find_all(exp.Table)
        if table.name and table.name.lower() not in ctes
    ]
    if not base_tables:
        raise LegacySqlPolicyError("SQL must read from the monitored table")

    expected_table = target_table.casefold()
    expected_schema = target_schema.casefold()
    for table in base_tables:
        if table.catalog:
            raise LegacySqlPolicyError("Cross-catalog references are not allowed")
        if table.name.casefold() != expected_table:
            raise LegacySqlPolicyError("SQL may only read from the monitored table")
        if not table.db:
            raise LegacySqlPolicyError(
                "Base-table references must include the monitored schema"
            )
        if table.db.casefold() != expected_schema:
            raise LegacySqlPolicyError("SQL may only read from the monitored schema")

    return query


def violation_count_from_result(result: dict) -> int:
    """Validate and convert the exact one-column scalar result contract."""
    if not isinstance(result, dict) or len(result) != 1:
        raise LegacySqlResultError(
            "Monitor SQL must return exactly one row with exactly one numeric column"
        )

    value = next(iter(result.values()))
    if isinstance(value, bool) or not isinstance(value, Number):
        raise LegacySqlResultError("Monitor result must be a numeric violation count")

    numeric = float(value)
    if not math.isfinite(numeric):
        raise LegacySqlResultError("Monitor result must be finite")
    if numeric < 0 or not numeric.is_integer() or numeric > MAX_VIOLATION_COUNT:
        raise LegacySqlResultError(
            "Monitor result must be a non-negative 64-bit integer"
        )
    return int(numeric)


async def execute_legacy_monitor(
    connector,
    sql: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[dict, int]:
    """Execute through the connector's restricted monitor path and validate output."""
    if timeout_seconds < 1 or timeout_seconds > 120:
        raise LegacySqlPolicyError("Monitor timeout must be between 1 and 120 seconds")

    execute = getattr(connector, "execute_monitor_query", None)
    if not callable(execute):
        raise LegacySqlPolicyError("Connector has no restricted monitor execution path")

    try:
        result = await asyncio.wait_for(
            execute(sql, timeout_seconds=timeout_seconds),
            timeout=timeout_seconds + 1,
        )
    except TimeoutError as exc:
        raise LegacySqlResultError(
            f"Monitor query exceeded the {timeout_seconds}-second timeout"
        ) from exc

    return result, violation_count_from_result(result)
