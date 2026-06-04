import logging
import time

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class DuckDBConnector(BaseConnector):
    """
    In-process DuckDB connector for local dev and jury demo.
    config: { 'path': '/path/to/file.duckdb' }  (or ':memory:')
    """

    def __init__(self, config: dict):
        self._config = config
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            import duckdb
            path = self._config.get("path", ":memory:")
            self._conn = duckdb.connect(path)
        return self._conn

    async def test_connection(self) -> bool:
        try:
            self._get_conn().execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning("DuckDB connection test failed: %s", e)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT table_schema, table_name,
                   estimated_size AS estimated_rows
            FROM duckdb_tables()
            ORDER BY table_schema, table_name
            """
        ).fetchall()
        schemas: dict[str, SchemaInfo] = {}
        for schema_name, table_name, est_rows in rows:
            if schema_name not in schemas:
                schemas[schema_name] = SchemaInfo(name=schema_name)
            schemas[schema_name].tables.append(TableInfo(name=table_name, estimated_rows=est_rows))
        return list(schemas.values())

    async def execute_profile_query(self, query: str) -> dict:
        conn = self._get_conn()
        result = conn.execute(query).fetchdf()
        if result.empty:
            return {}
        return result.iloc[0].to_dict()

    async def get_table_ddl(self, schema: str, table: str) -> str:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = ? AND table_name = ? "
            "ORDER BY ordinal_position",
            [schema, table],
        ).fetchall()
        lines = [f"  {col} {dtype} {'NULL' if nullable == 'YES' else 'NOT NULL'}"
                 for col, dtype, nullable in rows]
        return f"CREATE TABLE {schema}.{table} (\n" + ",\n".join(lines) + "\n);"

    async def test_connection_with_latency(self) -> tuple[bool, int]:
        start = time.monotonic()
        ok = await self.test_connection()
        ms = int((time.monotonic() - start) * 1000)
        return ok, ms

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
