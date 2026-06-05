import logging

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)

_SKIP_SCHEMAS = {"system", "information_schema", "INFORMATION_SCHEMA"}


class ClickHouseConnector(BaseConnector):
    """
    ClickHouse connector via clickhouse-connect (HTTP transport, async-friendly).
    Config: host, port (default 8123), database, username (default 'default'), password.
    """

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
            logger.warning("ClickHouse connection test failed: %s", e)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        client = await self._get_client()
        result = await client.query(
            """
            SELECT database, name, total_rows
            FROM system.tables
            WHERE engine NOT IN ('View','MaterializedView','Dictionary','Set','Join','Buffer')
              AND database NOT IN ('system','information_schema','INFORMATION_SCHEMA')
            ORDER BY database, name
            """
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
        result = await client.query(query)
        if result.result_rows:
            row = result.result_rows[0]
            cols = result.column_names
            return dict(zip(cols, row))
        return {}

    async def get_table_ddl(self, schema: str, table: str) -> str:
        client = await self._get_client()
        result = await client.query(
            "SELECT name, type, is_in_primary_key FROM system.columns WHERE database = {db:String} AND table = {tbl:String} ORDER BY position",
            parameters={"db": schema, "tbl": table},
        )
        lines = []
        for row in result.result_rows:
            col_name, col_type, _ = row
            lines.append(f"  `{col_name}` {col_type}")
        return f"CREATE TABLE `{schema}`.`{table}` (\n" + ",\n".join(lines) + "\n);"

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
