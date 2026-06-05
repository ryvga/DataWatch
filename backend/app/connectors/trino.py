import logging

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class TrinoConnector(BaseConnector):
    """
    Trino (and Presto-compatible) connector via trino-python-client.
    Config: host, port (default 8080), user, catalog, schema (optional), http_scheme (http/https).
    """

    def __init__(self, config: dict):
        self._config = config
        self._conn = None

    async def _get_conn(self):
        if self._conn is None:
            import asyncio
            import trino
            c = self._config
            loop = asyncio.get_event_loop()
            self._conn = await loop.run_in_executor(
                None,
                lambda: trino.dbapi.connect(
                    host=c.get("host", "localhost"),
                    port=int(c.get("port", 8080)),
                    user=c.get("user", c.get("username", "trino")),
                    catalog=c.get("catalog", "tpch"),
                    schema=c.get("schema", "tiny"),
                    http_scheme=c.get("http_scheme", "http"),
                    auth=trino.auth.BasicAuthentication(c["user"], c["password"]) if c.get("password") else None,
                ),
            )
        return self._conn

    async def _execute(self, query: str):
        import asyncio
        conn = await self._get_conn()
        loop = asyncio.get_event_loop()
        def _run():
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                desc = cur.description or []
                cols = [d[0] for d in desc]
                return rows, cols
        return await loop.run_in_executor(None, _run)

    async def test_connection(self) -> bool:
        try:
            await self._execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning("Trino connection test failed: %s", e)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        c = self._config
        catalog = c.get("catalog", "tpch")
        rows, _ = await self._execute(
            f"""
            SELECT table_schema, table_name
            FROM {catalog}.information_schema.tables
            WHERE table_type = 'BASE TABLE'
            ORDER BY table_schema, table_name
            """
        )
        schemas: dict[str, SchemaInfo] = {}
        for row in rows:
            s = row[0]
            if s not in schemas:
                schemas[s] = SchemaInfo(name=s)
            schemas[s].tables.append(TableInfo(name=row[1]))
        return list(schemas.values())

    async def execute_profile_query(self, query: str) -> dict:
        rows, cols = await self._execute(query)
        if rows:
            return dict(zip(cols, rows[0]))
        return {}

    async def get_table_ddl(self, schema: str, table: str) -> str:
        c = self._config
        catalog = c.get("catalog", "tpch")
        rows, _ = await self._execute(
            f"""
            SELECT column_name, data_type, is_nullable
            FROM {catalog}.information_schema.columns
            WHERE table_schema = '{schema}' AND table_name = '{table}'
            ORDER BY ordinal_position
            """
        )
        lines = [f"  {r[0]} {r[1]} {'NULL' if r[2]=='YES' else 'NOT NULL'}" for r in rows]
        return f"CREATE TABLE {schema}.{table} (\n" + ",\n".join(lines) + "\n);"

    async def close(self) -> None:
        if self._conn:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._conn.close)
            self._conn = None
