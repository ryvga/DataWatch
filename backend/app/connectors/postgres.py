import logging
import time

import psycopg
from psycopg.rows import dict_row

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class PostgresConnector(BaseConnector):
    """
    Async Postgres connector via psycopg3.
    Uses a single persistent connection per connector instance (no pool),
    which avoids event-loop teardown races with asyncio.run() in Celery tasks.
    """

    profile_dialect = "postgres"

    def __init__(self, config: dict):
        self._config = config
        self._conn: psycopg.AsyncConnection | None = None

    def _connect_kwargs(self) -> dict:
        """Keep credentials as driver parameters, never interpolate a libpq DSN."""
        c = self._config
        return {
            "host": c["host"],
            "port": int(c.get("port", 5432)),
            "dbname": c["database"],
            "user": c.get("username") or c.get("user", ""),
            "password": c.get("password", ""),
        }

    async def _get_conn(self) -> psycopg.AsyncConnection:
        if self._conn is None or self._conn.closed:
            self._conn = await psycopg.AsyncConnection.connect(
                row_factory=dict_row,
                **self._connect_kwargs(),
            )
        return self._conn

    async def test_connection(self) -> bool:
        try:
            conn = await self._get_conn()
            await conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning("Postgres connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        conn = await self._get_conn()
        rows = await conn.execute(
            """
            SELECT table_schema, table_name,
                   (xpath('/row/c/text()',
                          query_to_xml(format('SELECT COUNT(*) AS c FROM %I.%I',
                                              table_schema, table_name), FALSE, TRUE, ''))
                   )[1]::text::bigint AS estimated_rows
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
            """
        )
        schemas: dict[str, SchemaInfo] = {}
        async for row in rows:
            s = row["table_schema"]
            if s not in schemas:
                schemas[s] = SchemaInfo(name=s)
            schemas[s].tables.append(
                TableInfo(name=row["table_name"], estimated_rows=row["estimated_rows"])
            )
        return list(schemas.values())

    async def execute_profile_query(self, query: str) -> dict:
        conn = await self._get_conn()
        result = await conn.execute(query)
        row = await result.fetchone()
        return dict(row) if row else {}

    async def execute_monitor_query(
        self, query: str, *, timeout_seconds: int = 30
    ) -> dict:
        """Run a scalar query in a read-only transaction with server-side timeout."""
        conn = await self._get_conn()
        timeout_ms = timeout_seconds * 1000
        try:
            await conn.rollback()
            await conn.execute("SET TRANSACTION READ ONLY")
            await conn.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(timeout_ms),),
            )
            cursor = await conn.execute(query)
            rows = await cursor.fetchmany(2)
            if len(rows) != 1:
                raise ValueError("Monitor SQL must return exactly one row")
            return dict(rows[0])
        finally:
            await conn.rollback()

    async def execute_compiled_monitor(
        self,
        statement: str,
        parameters: dict,
        *,
        timeout_seconds: int = 30,
    ) -> dict:
        """Execute a compiler-produced aggregate with psycopg named bindings."""
        conn = await self._get_conn()
        timeout_ms = timeout_seconds * 1000
        try:
            await conn.rollback()
            await conn.execute("SET TRANSACTION READ ONLY")
            await conn.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(timeout_ms),),
            )
            cursor = await conn.execute(statement, parameters)
            rows = await cursor.fetchmany(2)
            if len(rows) != 1:
                raise ValueError("Compiled monitor must return exactly one row")
            return dict(rows[0])
        finally:
            await conn.rollback()

    async def get_table_ddl(self, schema: str, table: str) -> str:
        conn = await self._get_conn()
        rows = await conn.execute(
            """
            SELECT column_name, data_type, is_nullable,
                   character_maximum_length, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        lines = []
        async for row in rows:
            col = row["column_name"]
            dtype = row["data_type"]
            nullable = "NULL" if row["is_nullable"] == "YES" else "NOT NULL"
            quoted_col = '"' + col.replace('"', '""') + '"'
            lines.append(f"  {quoted_col} {dtype} {nullable}")
        return f"CREATE TABLE {schema}.{table} (\n" + ",\n".join(lines) + "\n);"

    async def close(self) -> None:
        if self._conn and not self._conn.closed:
            await self._conn.close()
            self._conn = None

    async def test_connection_with_latency(self) -> tuple[bool, int]:
        start = time.monotonic()
        ok = await self.test_connection()
        ms = int((time.monotonic() - start) * 1000)
        return ok, ms
