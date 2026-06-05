import logging

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class DatabricksConnector(BaseConnector):
    """
    Databricks SQL connector via databricks-sql-connector.
    Config: server_hostname, http_path, access_token, catalog (optional), schema (optional).
    """

    def __init__(self, config: dict):
        self._config = config
        self._conn = None

    async def _get_conn(self):
        if self._conn is None:
            import asyncio
            from databricks import sql as dbsql
            c = self._config
            # databricks-sql-connector is sync; run in thread executor
            loop = asyncio.get_event_loop()
            self._conn = await loop.run_in_executor(
                None,
                lambda: dbsql.connect(
                    server_hostname=c["server_hostname"],
                    http_path=c["http_path"],
                    access_token=c["access_token"],
                ),
            )
        return self._conn

    async def _execute(self, query: str, params=None):
        import asyncio
        conn = await self._get_conn()
        loop = asyncio.get_event_loop()
        def _run():
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall(), [d[0] for d in (cur.description or [])]
        return await loop.run_in_executor(None, _run)

    async def test_connection(self) -> bool:
        try:
            rows, _ = await self._execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning("Databricks connection test failed: %s", e)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        c = self._config
        catalog_filter = f"AND table_catalog = '{c['catalog']}'" if c.get("catalog") else ""
        rows, cols = await self._execute(
            f"""
            SELECT table_schema, table_name, NULL as est_rows
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              {catalog_filter}
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
        rows, _ = await self._execute(
            f"""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
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
