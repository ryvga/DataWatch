import logging

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)

_SKIP_SCHEMAS = {"system", "information_schema", "INFORMATION_SCHEMA"}


class ClickHouseConnector(BaseConnector):
    """
    ClickHouse connector via clickhouse-connect (HTTP transport, async-friendly).
    Config: host, port (default 8123), database, username (default 'default'), password.
    """

    profile_dialect = "clickhouse"

    def __init__(self, config: dict):
        self._config = config
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import clickhouse_connect
            c = self._config
            self._client = await clickhouse_connect.get_async_client(
                host=c.get("host", "localhost"),
                port=int(c.get("port", 8123)),
                database=c.get("database", "default"),
                username=c.get("username") or c.get("user", "default"),
                password=c.get("password", ""),
            )
        return self._client

    async def test_connection(self) -> bool:
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.warning("ClickHouse connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        client = await self._get_client()
        result = await client.query(
            """
            SELECT database, name, total_rows
            FROM system.tables
            WHERE engine NOT IN ('View','MaterializedView','Dictionary','Set','Join','Buffer')
              AND database NOT IN ('system','information_schema','INFORMATION_SCHEMA')
              AND database = {database:String}
            ORDER BY database, name
            """,
            parameters={"database": self._config.get("database", "default")},
        )
        schemas: dict[str, SchemaInfo] = {}
        for row in result.result_rows:
            db, tbl, total_rows = row
            if db not in schemas:
                schemas[db] = SchemaInfo(name=db)
            schemas[db].tables.append(TableInfo(name=tbl, estimated_rows=total_rows))
        return list(schemas.values())

    async def execute_profile_query(self, query: str) -> dict:
        client = await self._get_client()
        result = await client.query(
            query,
            settings={"readonly": 2, "max_execution_time": 120},
        )
        if result.result_rows:
            row = result.result_rows[0]
            cols = result.column_names
            return dict(zip(cols, row))
        return {}

    async def get_table_ddl(self, schema: str, table: str) -> str:
        _validate_identifier(schema)
        _validate_identifier(table)
        if schema != self._config.get("database", "default"):
            raise ValueError("ClickHouse schema access is restricted to the configured database")
        client = await self._get_client()
        result = await client.query(
            "SELECT name, type, is_in_primary_key FROM system.columns WHERE database = {db:String} AND table = {tbl:String} ORDER BY position",
            parameters={"db": schema, "tbl": table},
        )
        lines = []
        for row in result.result_rows:
            col_name, col_type, _ = row
            lines.append(f"  {_quote_identifier(col_name)} {col_type}")
        return (
            f"CREATE TABLE {_quote_identifier(schema)}.{_quote_identifier(table)} (\n"
            + ",\n".join(lines)
            + "\n);"
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None


def _validate_identifier(value: str) -> None:
    if not value or "\x00" in value:
        raise ValueError("ClickHouse identifiers must be non-empty and contain no NUL bytes")


def _quote_identifier(value: str) -> str:
    _validate_identifier(value)
    return "`" + value.replace("`", "``") + "`"
