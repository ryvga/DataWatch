import asyncio
import logging
from pathlib import Path
from urllib.parse import quote

import aiosqlite

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

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
            logger.warning("SQLite connection test failed: %s", e)
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

    async def get_table_ddl(self, schema: str, table: str) -> str:
        conn = await self._get_conn()
        async with conn.execute(
            "SELECT cid, name, type, \"notnull\", dflt_value, pk "
            "FROM pragma_table_info(?) ORDER BY cid",
            (table,),
        ) as cur:
            rows = await cur.fetchall()
        lines = []
        for row in rows:
            col_name = row[1]
            col_type = row[2] or "TEXT"
            notnull = "NOT NULL" if row[3] else "NULL"
            quoted_col = '"' + col_name.replace('"', '""') + '"'
            lines.append(f"  {quoted_col} {col_type} {notnull}")
        return f"CREATE TABLE {table} (\n" + ",\n".join(lines) + "\n);"

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
