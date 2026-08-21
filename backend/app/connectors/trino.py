import asyncio
import logging

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class TrinoConnector(BaseConnector):
    """
    Trino (and Presto-compatible) connector via trino-python-client.
    Config: host, port (default 8080), user, catalog, schema (optional), http_scheme (http/https).
    """

    profile_dialect = "trino"

    def __init__(self, config: dict):
        self._config = config
        self._conn = None

    async def _get_conn(self):
        if self._conn is None:
            import trino

            c = self._config
            auth = (
                trino.auth.BasicAuthentication(c.get("user", "trino"), c["password"])
                if c.get("password")
                else None
            )
            self._conn = await asyncio.to_thread(
                trino.dbapi.connect,
                    host=c.get("host", "localhost"),
                    port=int(c.get("port", 8080)),
                    user=c.get("user", c.get("username", "trino")),
                    catalog=c.get("catalog", "tpch"),
                    schema=c.get("schema", "tiny"),
                    http_scheme=c.get("http_scheme", "http"),
                    auth=auth,
            )
        return self._conn

    async def _execute(self, query: str, params=None):
        conn = await self._get_conn()

        def _run():
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
                desc = cur.description or []
                cols = [d[0] for d in desc]
                return rows, cols

        return await asyncio.to_thread(_run)

    async def test_connection(self) -> bool:
        try:
            await self._execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning("Trino connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        c = self._config
        schema_scope = c.get("schema")
        query = """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
        """
        parameters = None
        if schema_scope:
            query += " AND table_schema = ?"
            parameters = (schema_scope,)
        query += " ORDER BY table_schema, table_name"
        rows, _ = await self._execute(query, parameters)
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
        _validate_identifier(schema)
        _validate_identifier(table)
        configured_schema = self._config.get("schema")
        if configured_schema and schema != configured_schema:
            raise ValueError("Trino schema access is restricted to the configured schema")
        rows, _ = await self._execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        lines = [
            f"  {_quote_identifier(row[0])} {row[1]} "
            f"{'NULL' if row[2] == 'YES' else 'NOT NULL'}"
            for row in rows
        ]
        return (
            f"CREATE TABLE {_quote_identifier(schema)}.{_quote_identifier(table)} (\n"
            + ",\n".join(lines)
            + "\n);"
        )

    async def close(self) -> None:
        if self._conn:
            await asyncio.to_thread(self._conn.close)
            self._conn = None


def _validate_identifier(value: str) -> None:
    if not value or "\x00" in value:
        raise ValueError("Trino identifiers must be non-empty and contain no NUL bytes")


def _quote_identifier(value: str) -> str:
    _validate_identifier(value)
    return '"' + value.replace('"', '""') + '"'
