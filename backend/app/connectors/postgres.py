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

    def __init__(self, config: dict):
        self._config = config
        self._conn: psycopg.AsyncConnection | None = None

    def _dsn(self) -> str:
        c = self._config
        user = c.get('username') or c.get('user', '')
        return (
            f"host={c['host']} port={c.get('port', 5432)} "
            f"dbname={c['database']} user={user} password={c['password']}"
        )

    async def _get_conn(self) -> psycopg.AsyncConnection:
        if self._conn is None or self._conn.closed:
            self._conn = await psycopg.AsyncConnection.connect(
                self._dsn(), row_factory=dict_row
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
            lines.append(f"  {col} {dtype} {nullable}")
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
