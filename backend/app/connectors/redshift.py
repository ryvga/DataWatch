import logging

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)

# Redshift is Postgres-compatible — use psycopg3 with Redshift endpoint
_SKIP_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast", "pg_internal"}


class RedshiftConnector(BaseConnector):
    """
    Redshift connector via psycopg3 (Redshift is wire-compatible with Postgres).
    Config: host, port (default 5439), database, username, password.
    """

    def __init__(self, config: dict):
        self._config = config
        self._conn = None

    def _dsn(self) -> str:
        c = self._config
        user = c.get("username") or c.get("user", "")
        return (
            f"host={c['host']} port={c.get('port', 5439)} "
            f"dbname={c['database']} user={user} password={c['password']} "
            "sslmode=require"
        )

    async def _get_conn(self):
        if self._conn is None or self._conn.closed:
            import psycopg
            from psycopg.rows import dict_row
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
            logger.warning("Redshift connection test failed: %s", e)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        conn = await self._get_conn()
        rows = await conn.execute(
            """
            SELECT schemaname, tablename
            FROM pg_catalog.svv_tables
            WHERE table_type = 'BASE TABLE'
              AND schemaname NOT IN ('pg_catalog','information_schema','pg_toast','pg_internal')
            ORDER BY schemaname, tablename
            """
        )
        schemas: dict[str, SchemaInfo] = {}
        async for row in rows:
            s = row["schemaname"]
            if s not in schemas:
                schemas[s] = SchemaInfo(name=s)
            schemas[s].tables.append(TableInfo(name=row["tablename"]))
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
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        lines = []
        async for row in rows:
            null = "NULL" if row["is_nullable"] == "YES" else "NOT NULL"
            lines.append(f"  {row['column_name']} {row['data_type']} {null}")
        return f"CREATE TABLE {schema}.{table} (\n" + ",\n".join(lines) + "\n);"

    async def close(self) -> None:
        if self._conn and not self._conn.closed:
            await self._conn.close()
            self._conn = None
