import logging

import aiosqlite

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class SQLiteConnector(BaseConnector):
    """
    SQLite connector via aiosqlite.
    Config: path (file path to .db file, or ':memory:').
    """

    def __init__(self, config: dict):
        self._path = config.get("path", ":memory:")
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._path)
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

    async def get_table_ddl(self, schema: str, table: str) -> str:
        conn = await self._get_conn()
        async with conn.execute(
            f"PRAGMA table_info('{table}')"
        ) as cur:
            rows = await cur.fetchall()
        lines = []
        for row in rows:
            col_name = row[1]
            col_type = row[2] or "TEXT"
            notnull = "NOT NULL" if row[3] else "NULL"
            lines.append(f"  {col_name} {col_type} {notnull}")
        return f"CREATE TABLE {table} (\n" + ",\n".join(lines) + "\n);"

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
