import asyncio
import logging
from pathlib import Path
from urllib.parse import quote

import aiosqlite

from app.connectors.base import (
    BaseConnector,
    ConnectorConfigurationError,
    SchemaInfo,
    TableInfo,
)

logger = logging.getLogger(__name__)


class SQLiteConnector(BaseConnector):
    """
    SQLite connector via aiosqlite.
    Config: path (file path to .db file, or ':memory:').
    """

    profile_dialect = "sqlite"

    def __init__(self, config: dict):
        self._path = config.get("path", ":memory:")
        self._conn: aiosqlite.Connection | None = None
        self._column_cache: dict[str, list[aiosqlite.Row]] = {}

    @staticmethod
    def _validate_schema(schema: str) -> None:
        if schema != "main":
            raise ConnectorConfigurationError("SQLite only supports the main schema.")

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        if not identifier or "\x00" in identifier:
            raise ConnectorConfigurationError(
                "SQLite identifiers must be non-empty and contain no NUL bytes."
            )
        return '"' + identifier.replace('"', '""') + '"'

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            if self._path == ":memory:":
                self._conn = await aiosqlite.connect(self._path)
                await self._conn.execute("PRAGMA query_only = ON")
            else:
                encoded_path = quote(str(Path(self._path).resolve()), safe="/")
                self._conn = await aiosqlite.connect(
                    f"file:{encoded_path}?mode=ro", uri=True
                )
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def test_connection(self) -> bool:
        try:
            conn = await self._get_conn()
            await conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning("SQLite connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()
        schema = SchemaInfo(name="main")
        for row in rows:
            schema.tables.append(TableInfo(name=row[0]))
        return [schema]

    async def execute_profile_query(self, query: str) -> dict:
        conn = await self._get_conn()
        async with conn.execute(query) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
        return {}

    async def execute_monitor_query(
        self, query: str, *, timeout_seconds: int = 30
    ) -> dict:
        """Run one scalar query on a query-only/read-only SQLite connection."""
        conn = await self._get_conn()

        async def run_query() -> dict:
            async with conn.execute(query) as cursor:
                rows = await cursor.fetchmany(2)
                if len(rows) != 1:
                    raise ValueError("Monitor SQL must return exactly one row")
                return dict(rows[0])

        task = asyncio.create_task(run_query())
        done, _ = await asyncio.wait({task}, timeout=timeout_seconds)
        if not done:
            await conn.interrupt()
            try:
                await task
            except Exception:
                pass
            raise TimeoutError
        return task.result()

    async def execute_compiled_monitor(
        self,
        statement: str,
        parameters: dict,
        *,
        timeout_seconds: int = 30,
    ) -> dict:
        """Execute a compiler-produced aggregate with SQLite named bindings."""
        conn = await self._get_conn()

        async def run_query() -> dict:
            async with conn.execute(statement, parameters) as cursor:
                rows = await cursor.fetchmany(2)
                if len(rows) != 1:
                    raise ValueError("Compiled monitor must return exactly one row")
                return dict(rows[0])

        task = asyncio.create_task(run_query())
        done, _ = await asyncio.wait({task}, timeout=timeout_seconds)
        if not done:
            await conn.interrupt()
            try:
                await task
            except Exception:
                pass
            raise TimeoutError
        return task.result()

    async def _get_columns(self, schema: str, table: str) -> list[aiosqlite.Row]:
        self._validate_schema(schema)
        if table in self._column_cache:
            return self._column_cache[table]
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT cid, name, type, \"notnull\", dflt_value, pk "
            "FROM pragma_table_info(?) ORDER BY cid",
            (table,),
        ) as cur:
            rows = list(await cur.fetchall())
        if not rows:
            raise ConnectorConfigurationError(
                "SQLite table schema could not be verified."
            )
        self._column_cache[table] = rows
        return rows

    async def get_table_ddl(self, schema: str, table: str) -> str:
        rows = await self._get_columns(schema, table)
        lines = []
        for row in rows:
            col_name = row[1]
            col_type = row[2] or "TEXT"
            notnull = "NOT NULL" if row[3] else "NULL"
            quoted_col = self._quote_identifier(col_name)
            lines.append(f"  {quoted_col} {col_type} {notnull}")
        return (
            f"CREATE TABLE {self._quote_identifier(table)} (\n"
            + ",\n".join(lines)
            + "\n);"
        )

    async def get_table_schema(
        self, schema: str, table: str
    ) -> tuple[str, set[str] | None]:
        rows = await self._get_columns(schema, table)
        return await self.get_table_ddl(schema, table), {str(row[1]) for row in rows}

    async def validate_profile_config(
        self,
        schema: str,
        table: str,
        freshness_column: str | None,
    ) -> None:
        if freshness_column is None:
            return
        rows = await self._get_columns(schema, table)
        column = next((row for row in rows if row[1] == freshness_column), None)
        if column is None:
            raise ConnectorConfigurationError(
                "SQLite freshness_column must exist in the verified table schema."
            )
        declared_type = str(column[2] or "").upper()
        type_parts = declared_type.replace("(", " ", 1).split(maxsplit=1)
        base_type = type_parts[0] if type_parts else ""
        if base_type not in {
            "DATE",
            "DATETIME",
            "TIMESTAMP",
            "TIMESTAMPTZ",
            "TIMESTAMP_TZ",
        }:
            raise ConnectorConfigurationError(
                "SQLite freshness_column must declare DATE, DATETIME, or TIMESTAMP."
            )

        conn = await self._get_conn()
        safe_column = self._quote_identifier(freshness_column)
        safe_table = self._quote_identifier(table)
        async with conn.execute(
            "SELECT COUNT(*) AS observed, "
            "SUM(CASE WHEN julianday(value) IS NULL THEN 1 ELSE 0 END) AS invalid "
            "FROM ("
            f"SELECT {safe_column} AS value FROM {safe_table} "
            f"WHERE {safe_column} IS NOT NULL LIMIT 32"
            ")"
        ) as cur:
            probe = await cur.fetchone()
        if probe and int(probe[0] or 0) > 0 and int(probe[1] or 0) > 0:
            raise ConnectorConfigurationError(
                "SQLite freshness_column contains values that are not parseable dates."
            )

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
        self._column_cache.clear()
