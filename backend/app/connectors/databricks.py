import asyncio
import logging

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class DatabricksConnector(BaseConnector):
    """
    Databricks SQL connector via databricks-sql-connector.
    Config: server_hostname, http_path, access_token, catalog (optional), schema (optional).
    """

    profile_dialect = "databricks"

    def __init__(self, config: dict):
        self._config = config
        self._conn = None

    async def _get_conn(self):
        if self._conn is None:
            from databricks import sql as dbsql

            c = self._config
            self._conn = await asyncio.to_thread(
                dbsql.connect,
                    server_hostname=c["server_hostname"],
                    http_path=c["http_path"],
                    access_token=c["access_token"],
                    catalog=c.get("catalog", "hive_metastore"),
                    schema=c.get("schema", "default"),
            )
        return self._conn

    async def _execute(self, query: str, params=None):
        conn = await self._get_conn()

        def _run():
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall(), [d[0] for d in (cur.description or [])]

        return await asyncio.to_thread(_run)

    async def test_connection(self) -> bool:
        try:
            rows, _ = await self._execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning("Databricks connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        c = self._config
        catalog = c.get("catalog", "hive_metastore")
        schema = c.get("schema")
        query = """
            SELECT table_schema, table_name, NULL as est_rows
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_catalog = ?
        """
        parameters = [catalog]
        if schema:
            query += " AND table_schema = ?"
            parameters.append(schema)
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
            raise ValueError("Databricks schema access is restricted to the configured schema")
        rows, _ = await self._execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_catalog = ? AND table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            [self._config.get("catalog", "hive_metastore"), schema, table],
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
        raise ValueError("Databricks identifiers must be non-empty and contain no NUL bytes")


def _quote_identifier(value: str) -> str:
    _validate_identifier(value)
    return "`" + value.replace("`", "``") + "`"
