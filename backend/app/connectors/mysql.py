import asyncio
import logging
import re
import ssl

from app.connectors.base import (
    BaseConnector,
    ConnectorConfigurationError,
    ScanBudgetExceeded,
    SchemaInfo,
    TableInfo,
)

logger = logging.getLogger(__name__)

_SKIP_SCHEMAS = {"sys", "mysql", "information_schema", "performance_schema"}


class MySQLConnector(BaseConnector):
    """Async MySQL/MariaDB connector via aiomysql."""

    profile_dialect = "mysql"
    monitor_dialect = "mysql"

    def __init__(self, config: dict):
        self._config = config
        self._pool = None
        self._column_cache: dict[tuple[str, str], list[tuple]] = {}

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        if not identifier or "\x00" in identifier:
            raise ValueError("MySQL identifiers must be non-empty and contain no NUL bytes")
        return f"`{identifier.replace('`', '``')}`"

    def _ssl_context(self) -> ssl.SSLContext | None:
        """Require certificate and hostname verification unless explicitly disabled."""
        mode = str(self._config.get("tls_mode", "verify_identity")).lower()
        if mode == "disabled":
            return None
        if mode != "verify_identity":
            raise ValueError("tls_mode must be 'verify_identity' or 'disabled'")

        ca_pem = self._config.get("ssl_ca") or None
        context = ssl.create_default_context(cadata=ca_pem)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        return context

    async def _get_pool(self):
        if self._pool is None:
            import aiomysql
            c = self._config
            self._pool = await aiomysql.create_pool(
                host=c.get("host", "localhost"),
                port=int(c.get("port", 3306)),
                db=c["database"],
                user=c.get("username") or c.get("user", ""),
                password=c.get("password", ""),
                ssl=self._ssl_context(),
                autocommit=True,
                minsize=1,
                maxsize=2,
            )
        return self._pool

    async def test_connection(self) -> bool:
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning("MySQL connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT table_schema, table_name, table_rows
                    FROM information_schema.tables
                    WHERE table_type = 'BASE TABLE'
                      AND table_schema NOT IN (%s,%s,%s,%s)
                    ORDER BY table_schema, table_name
                    """,
                    tuple(_SKIP_SCHEMAS),
                )
                rows = await cur.fetchall()
        schemas: dict[str, SchemaInfo] = {}
        for row in rows:
            s = row[0]
            if s not in schemas:
                schemas[s] = SchemaInfo(name=s)
            schemas[s].tables.append(TableInfo(name=row[1], estimated_rows=row[2]))
        return list(schemas.values())

    async def execute_profile_query(self, query: str) -> dict:
        import aiomysql

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query)
                row = await cur.fetchone()
                return dict(row) if row else {}

    @staticmethod
    def _bind_compiled_parameters(statement: str, parameters: dict) -> tuple[str, tuple]:
        values = []

        def replace(match):
            values.append(parameters[match.group(1)])
            return "%s"

        bound = re.sub(r":(p\d+)\b", replace, statement)
        return bound, tuple(values)

    async def execute_compiled_monitor(
        self,
        statement: str,
        parameters: dict,
        *,
        timeout_seconds: int = 30,
    ) -> dict:
        """Execute one compiled aggregate in a database read-only transaction."""
        import aiomysql

        pool = await self._get_pool()
        bound, values = self._bind_compiled_parameters(statement, parameters)
        async with pool.acquire() as conn:
            async def run_query() -> dict:
                try:
                    async with conn.cursor(aiomysql.DictCursor) as cur:
                        await cur.execute("START TRANSACTION READ ONLY")
                        await cur.execute(bound, values)
                        rows = await cur.fetchmany(2)
                        if len(rows) != 1:
                            raise ValueError("Compiled monitor must return exactly one row")
                        return dict(rows[0])
                finally:
                    await conn.rollback()

            try:
                return await asyncio.wait_for(run_query(), timeout=timeout_seconds)
            except TimeoutError:
                conn.close()
                raise

    async def enforce_monitor_scan_budget(
        self,
        schema: str,
        table: str,
        max_bytes_scanned: int,
    ) -> None:
        """Bound scans by MySQL/MariaDB table plus index storage."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COALESCE(data_length, 0) + COALESCE(index_length, 0) "
                    "FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = %s",
                    (schema, table),
                )
                row = await cur.fetchone()
        if not row or int(row[0]) > max_bytes_scanned:
            raise ScanBudgetExceeded

    async def _get_columns(self, schema: str, table: str) -> list[tuple]:
        cache_key = (schema, table)
        if cache_key in self._column_cache:
            return self._column_cache[cache_key]
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT column_name, column_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema, table),
                )
                rows = list(await cur.fetchall())
        if not rows:
            raise ConnectorConfigurationError(
                "MySQL/MariaDB table schema could not be verified."
            )
        self._column_cache[cache_key] = rows
        return rows

    async def get_table_ddl(self, schema: str, table: str) -> str:
        rows = await self._get_columns(schema, table)
        lines = [
            f"  {self._quote_identifier(r[0])} {r[1]} "
            f"{'NULL' if r[2] == 'YES' else 'NOT NULL'}"
            for r in rows
        ]
        return (
            f"CREATE TABLE {self._quote_identifier(schema)}."
            f"{self._quote_identifier(table)} (\n"
            + ",\n".join(lines)
            + "\n);"
        )

    async def get_table_schema(
        self, schema: str, table: str
    ) -> tuple[str, set[str] | None]:
        rows = await self._get_columns(schema, table)
        return await self.get_table_ddl(schema, table), {str(row[0]) for row in rows}

    async def validate_profile_config(
        self,
        schema: str,
        table: str,
        freshness_column: str | None,
    ) -> None:
        if freshness_column is None:
            return
        rows = await self._get_columns(schema, table)
        column = next((row for row in rows if row[0] == freshness_column), None)
        if column is None:
            raise ConnectorConfigurationError(
                "MySQL/MariaDB freshness_column must exist in the verified table schema."
            )
        data_type = str(column[1]).lower().split("(", 1)[0].strip()
        if data_type not in {"date", "datetime", "timestamp"}:
            raise ConnectorConfigurationError(
                "MySQL/MariaDB freshness_column must use a date, datetime, or timestamp type."
            )

    async def close(self) -> None:
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
        self._column_cache.clear()
