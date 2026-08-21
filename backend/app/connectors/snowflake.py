import asyncio
import logging

from app.connectors.base import BaseConnector, ConnectorConfigurationError, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class SnowflakeConnector(BaseConnector):
    """Scoped Snowflake adapter using the synchronous SDK behind thread boundaries."""

    profile_dialect = "snowflake"

    def __init__(self, config: dict):
        self._config = config
        self._conn = None
        self._connection_lock = asyncio.Lock()

    def _timeout_seconds(self) -> int:
        try:
            value = int(self._config.get("query_timeout_seconds", 120))
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigurationError("Snowflake query_timeout_seconds must be an integer") from exc
        if not 1 <= value <= 600:
            raise ConnectorConfigurationError("Snowflake query_timeout_seconds must be between 1 and 600")
        return value

    def _connect_sync(self):
        import snowflake.connector

        config = self._config
        return snowflake.connector.connect(
            account=config["account"],
            user=config["user"],
            password=config.get("password", ""),
            database=config["database"],
            schema=config.get("schema", "PUBLIC"),
            warehouse=config.get("warehouse", "COMPUTE_WH"),
            login_timeout=min(self._timeout_seconds(), 60),
            network_timeout=self._timeout_seconds(),
            socket_timeout=self._timeout_seconds(),
            client_session_keep_alive=False,
            session_parameters={
                "STATEMENT_TIMEOUT_IN_SECONDS": self._timeout_seconds(),
                "QUERY_TAG": "panopta-profile",
            },
        )

    async def _get_conn(self):
        if self._conn is None or getattr(self._conn, "is_closed", lambda: True)():
            async with self._connection_lock:
                if self._conn is None or getattr(self._conn, "is_closed", lambda: True)():
                    self._conn = await asyncio.to_thread(self._connect_sync)
        return self._conn

    @staticmethod
    def _fetch_sync(conn, statement: str, parameters=None):
        with conn.cursor() as cursor:
            cursor.execute(statement, parameters)
            rows = cursor.fetchall()
            columns = [item[0] for item in (cursor.description or [])]
            return rows, columns

    async def _fetch(self, statement: str, parameters=None):
        conn = await self._get_conn()
        return await asyncio.to_thread(self._fetch_sync, conn, statement, parameters)

    async def test_connection(self) -> bool:
        try:
            self._timeout_seconds()
            await self._fetch("SELECT 1")
            return True
        except Exception as exc:
            logger.warning("Snowflake connection test failed: %s", type(exc).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        schema_scope = self._config.get("schema")
        statement = """
            SELECT table_schema, table_name, row_count
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema != 'INFORMATION_SCHEMA'
        """
        parameters = None
        if schema_scope:
            statement += " AND table_schema = %s"
            parameters = (schema_scope,)
        statement += " ORDER BY table_schema, table_name"
        rows, _ = await self._fetch(statement, parameters)
        schemas: dict[str, SchemaInfo] = {}
        for schema_name, table_name, estimated_rows in rows:
            schema = schemas.setdefault(schema_name, SchemaInfo(name=schema_name))
            schema.tables.append(TableInfo(name=table_name, estimated_rows=estimated_rows))
        return list(schemas.values())

    async def execute_profile_query(self, query: str) -> dict:
        rows, columns = await self._fetch(query)
        if not rows:
            return {}
        return dict(zip(columns, rows[0]))

    async def get_table_ddl(self, schema: str, table: str) -> str:
        _validate_identifier(schema)
        _validate_identifier(table)
        schema_scope = self._config.get("schema")
        if schema_scope and schema != schema_scope:
            raise ValueError("Snowflake schema access is restricted to the configured schema")
        rows, _ = await self._fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        lines = [
            f"  {_quote_identifier(name)} {data_type} "
            f"{'NULL' if is_nullable == 'YES' else 'NOT NULL'}"
            for name, data_type, is_nullable in rows
        ]
        return (
            f"CREATE TABLE {_quote_identifier(schema)}.{_quote_identifier(table)} (\n"
            + ",\n".join(lines)
            + "\n);"
        )

    async def close(self) -> None:
        conn = self._conn
        self._conn = None
        if conn is not None and not getattr(conn, "is_closed", lambda: True)():
            await asyncio.to_thread(conn.close)


def _validate_identifier(value: str) -> None:
    if not value or "\x00" in value:
        raise ValueError("Snowflake identifiers must be non-empty and contain no NUL bytes")


def _quote_identifier(value: str) -> str:
    _validate_identifier(value)
    return '"' + value.replace('"', '""') + '"'
