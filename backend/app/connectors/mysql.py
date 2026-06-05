import logging

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)

_SKIP_SCHEMAS = {"sys", "mysql", "information_schema", "performance_schema"}


class MySQLConnector(BaseConnector):
    """Async MySQL/MariaDB connector via aiomysql."""

    def __init__(self, config: dict):
        self._config = config
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            import aiomysql
            c = self._config
            self._pool = await aiomysql.create_pool(
                host=c.get("host", "localhost"),
                port=int(c.get("port", 3306)),
                db=c["database"],
                user=c.get("username") or c.get("user", ""),
                password=c.get("password", ""),
                autocommit=True,
                minsize=1,
                maxsize=2,
            )
        return self._pool

    async def test_connection(self) -> bool:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning("MySQL connection test failed: %s", e)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT table_schema, table_name, table_rows
                    FROM information_schema.tables
                    WHERE table_type = 'BASE TABLE'
                      AND table_schema NOT IN (%s,%s,%s,%s)
                    ORDER BY table_schema, table_name
                    """,
                    tuple(_SKIP_SCHEMAS),
                )
                rows = await cur.fetchall()
        schemas: dict[str, SchemaInfo] = {}
        for row in rows:
            s = row[0]
            if s not in schemas:
                schemas[s] = SchemaInfo(name=s)
            schemas[s].tables.append(TableInfo(name=row[1], estimated_rows=row[2]))
        return list(schemas.values())

    async def execute_profile_query(self, query: str) -> dict:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                import aiomysql
                await cur.execute(query)
                row = await cur.fetchone()
                return dict(row) if row else {}

    async def get_table_ddl(self, schema: str, table: str) -> str:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT column_name, column_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema, table),
                )
                rows = await cur.fetchall()
        lines = [f"  {r[0]} {r[1]} {'NULL' if r[2] == 'YES' else 'NOT NULL'}" for r in rows]
        return f"CREATE TABLE `{schema}`.`{table}` (\n" + ",\n".join(lines) + "\n);"

    async def close(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
