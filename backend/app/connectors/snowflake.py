from app.connectors.base import BaseConnector, SchemaInfo


class SnowflakeConnector(BaseConnector):
    """Snowflake connector — stub. Returns 501 via API."""

    def __init__(self, config: dict):
        self._config = config

    async def test_connection(self) -> bool:
        raise NotImplementedError("Snowflake connector coming soon")

    async def discover_schemas(self) -> list[SchemaInfo]:
        raise NotImplementedError("Snowflake connector coming soon")

    async def execute_profile_query(self, query: str) -> dict:
        raise NotImplementedError("Snowflake connector coming soon")

    async def get_table_ddl(self, schema: str, table: str) -> str:
        raise NotImplementedError("Snowflake connector coming soon")
