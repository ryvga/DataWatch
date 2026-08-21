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

    profile_dialect = "redshift"

    def __init__(self, config: dict):
        self._config = config
        self._conn = None

    def _connect_kwargs(self) -> dict:
        c = self._config
        user = c.get("username") or c.get("user", "")
        return {
            "host": c["host"],
            "port": int(c.get("port", 5439)),
            "dbname": c["database"],
            "user": user,
            "password": c["password"],
            "sslmode": "require",
        }

    async def _get_conn(self):
        if self._conn is None or self._conn.closed:
            import psycopg
            from psycopg.rows import dict_row
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
            logger.warning("Redshift connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        conn = await self._get_conn()
        query = """
            SELECT schemaname, tablename
            FROM pg_catalog.svv_tables
            WHERE table_type = 'BASE TABLE'
              AND schemaname NOT IN ('pg_catalog','information_schema','pg_toast','pg_internal')
        """
        parameters = None
        if self._config.get("schema"):
            query += " AND schemaname = %s"
            parameters = (self._config["schema"],)
        query += " ORDER BY schemaname, tablename"
        rows = await conn.execute(query, parameters)
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
        _validate_identifier(schema)
        _validate_identifier(table)
        if self._config.get("schema") and schema != self._config["schema"]:
            raise ValueError("Redshift schema access is restricted to the configured schema")
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
            lines.append(f"  {_quote_identifier(row['column_name'])} {row['data_type']} {null}")
        return (
            f"CREATE TABLE {_quote_identifier(schema)}.{_quote_identifier(table)} (\n"
            + ",\n".join(lines)
            + "\n);"
        )

    async def close(self) -> None:
        if self._conn and not self._conn.closed:
            await self._conn.close()
            self._conn = None


def _validate_identifier(value: str) -> None:
    if not value or "\x00" in value:
        raise ValueError("Redshift identifiers must be non-empty and contain no NUL bytes")


def _quote_identifier(value: str) -> str:
    _validate_identifier(value)
    return '"' + value.replace('"', '""') + '"'
