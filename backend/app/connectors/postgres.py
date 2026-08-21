import logging
import time

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.connectors.base import BaseConnector, ScanBudgetExceeded, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)


class PostgresConnector(BaseConnector):
    """
    Async Postgres connector via psycopg3.
    Uses a single persistent connection per connector instance (no pool),
    which avoids event-loop teardown races with asyncio.run() in Celery tasks.
    """

    profile_dialect = "postgres"
    monitor_dialect = "postgres"

    def __init__(self, config: dict):
        self._config = config
        self._conn: psycopg.AsyncConnection | None = None

    def _connect_kwargs(self) -> dict:
        """Keep credentials as driver parameters, never interpolate a libpq DSN."""
        c = self._config
        return {
            "host": c["host"],
            "port": int(c.get("port", 5432)),
            "dbname": c["database"],
            "user": c.get("username") or c.get("user", ""),
            "password": c.get("password", ""),
        }

    async def _get_conn(self) -> psycopg.AsyncConnection:
        if self._conn is None or self._conn.closed:
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
            logger.warning("Postgres connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        conn = await self._get_conn()
        rows = await conn.execute(
            """
            SELECT table_schema, table_name,
                   (xpath('/row/c/text()',
                          query_to_xml(format('SELECT COUNT(*) AS c FROM %I.%I',
                                              table_schema, table_name), FALSE, TRUE, ''))
                   )[1]::text::bigint AS estimated_rows
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY table_schema, table_name
            """
        )
        schemas: dict[str, SchemaInfo] = {}
        async for row in rows:
            s = row["table_schema"]
            if s not in schemas:
                schemas[s] = SchemaInfo(name=s)
            schemas[s].tables.append(
                TableInfo(name=row["table_name"], estimated_rows=row["estimated_rows"])
            )
        return list(schemas.values())

    async def execute_profile_query(self, query: str) -> dict:
        conn = await self._get_conn()
        result = await conn.execute(query)
        row = await result.fetchone()
        return dict(row) if row else {}

    async def execute_monitor_query(
        self, query: str, *, timeout_seconds: int = 30
    ) -> dict:
        """Run a scalar query in a read-only transaction with server-side timeout."""
        conn = await self._get_conn()
        timeout_ms = timeout_seconds * 1000
        try:
            await conn.rollback()
            await conn.execute("SET TRANSACTION READ ONLY")
            await conn.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(timeout_ms),),
            )
            cursor = await conn.execute(query)
            rows = await cursor.fetchmany(2)
            if len(rows) != 1:
                raise ValueError("Monitor SQL must return exactly one row")
            return dict(rows[0])
        finally:
            await conn.rollback()

    async def execute_compiled_monitor(
        self,
        statement: str,
        parameters: dict,
        *,
        timeout_seconds: int = 30,
    ) -> dict:
        """Execute a compiler-produced aggregate with psycopg named bindings."""
        conn = await self._get_conn()
        timeout_ms = timeout_seconds * 1000
        try:
            await conn.rollback()
            await conn.execute("SET TRANSACTION READ ONLY")
            await conn.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(timeout_ms),),
            )
            cursor = await conn.execute(statement, parameters)
            rows = await cursor.fetchmany(2)
            if len(rows) != 1:
                raise ValueError("Compiled monitor must return exactly one row")
            return dict(rows[0])
        finally:
            await conn.rollback()

    async def enforce_monitor_scan_budget(
        self,
        schema: str,
        table: str,
        max_bytes_scanned: int,
    ) -> None:
        """Use total relation storage as a conservative upper scan bound."""
        conn = await self._get_conn()
        escaped_schema = schema.replace('"', '""')
        escaped_table = table.replace('"', '""')
        qualified_relation = f'"{escaped_schema}"."{escaped_table}"'
        try:
            await conn.rollback()
            await conn.execute("SET TRANSACTION READ ONLY")
            cursor = await conn.execute(
                "SELECT pg_total_relation_size(%s::regclass) AS bytes",
                (qualified_relation,),
            )
            row = await cursor.fetchone()
            relation_bytes = int(row["bytes"]) if row else max_bytes_scanned + 1
            if relation_bytes > max_bytes_scanned:
                raise ScanBudgetExceeded
        finally:
            await conn.rollback()

    async def get_table_ddl(self, schema: str, table: str) -> str:
        conn = await self._get_conn()
        rows = await conn.execute(
            """
            SELECT column_name, data_type, is_nullable,
                   character_maximum_length, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        lines = []
        async for row in rows:
            col = row["column_name"]
            dtype = row["data_type"]
            nullable = "NULL" if row["is_nullable"] == "YES" else "NOT NULL"
            quoted_col = '"' + col.replace('"', '""') + '"'
            lines.append(f"  {quoted_col} {dtype} {nullable}")
        return f"CREATE TABLE {schema}.{table} (\n" + ",\n".join(lines) + "\n);"

    async def collect_rag_governance_observation(
        self,
        *,
        source_schema: str,
        source_table: str,
        source_key: str,
        source_updated_at: str | None,
        source_deleted_at: str | None,
        vector_schema: str,
        vector_table: str,
        vector_source_key: str,
        vector_updated_at: str | None,
        timeout_seconds: int = 30,
        max_bytes_scanned: int = 100_000_000,
    ) -> dict:
        """Collect bounded pgvector supply-chain counts and effective table grants.

        Identifiers are composed with psycopg's identifier API. The query returns
        aggregate counts and role metadata only; rows and embeddings never leave the
        customer database.
        """
        await self.enforce_monitor_scan_budget(source_schema, source_table, max_bytes_scanned)
        await self.enforce_monitor_scan_budget(vector_schema, vector_table, max_bytes_scanned)
        conn = await self._get_conn()
        q = sql.SQL
        ident = sql.Identifier
        stale_expression = q("FALSE")
        if source_updated_at and vector_updated_at:
            stale_expression = q("v.{} < s.{}").format(
                ident(vector_updated_at), ident(source_updated_at)
            )
        deletion_expression = q("FALSE")
        if source_deleted_at:
            deletion_expression = q("s.{} IS NOT NULL").format(ident(source_deleted_at))
        statement = q(
            """
            WITH source_metrics AS (
              SELECT
                COUNT(*) FILTER (WHERE v.{vector_key} IS NULL)::bigint AS missing_embeddings,
                COUNT(*) FILTER (WHERE v.{vector_key} IS NOT NULL AND ({stale}))::bigint AS stale_embeddings,
                COUNT(*) FILTER (WHERE v.{vector_key} IS NOT NULL AND ({deleted}))::bigint AS deletion_propagation_failures
              FROM {source_relation} AS s
              LEFT JOIN {vector_relation} AS v ON v.{vector_key} = s.{source_key}
            ), orphan_metrics AS (
              SELECT COUNT(*) FILTER (WHERE s.{source_key} IS NULL)::bigint AS orphan_embeddings
              FROM {vector_relation} AS v
              LEFT JOIN {source_relation} AS s ON s.{source_key} = v.{vector_key}
            ), grants AS (
              SELECT
                COALESCE(jsonb_agg(DISTINCT grantee ORDER BY grantee), '[]'::jsonb) AS roles,
                COALESCE(
                  jsonb_agg(jsonb_build_object('role', grantee, 'privilege', privilege_type)
                            ORDER BY grantee, privilege_type),
                  '[]'::jsonb
                ) AS effective_grants
              FROM (
                SELECT DISTINCT grantee, privilege_type
                FROM information_schema.role_table_grants
                WHERE ((table_schema = %s AND table_name = %s)
                    OR (table_schema = %s AND table_name = %s))
                  AND privilege_type IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE')
              ) grant_rows
            )
            SELECT source_metrics.*, orphan_metrics.orphan_embeddings,
                   grants.roles AS effective_roles, grants.effective_grants
            FROM source_metrics CROSS JOIN orphan_metrics CROSS JOIN grants
            """
        ).format(
            source_relation=q("{}.{}").format(ident(source_schema), ident(source_table)),
            vector_relation=q("{}.{}").format(ident(vector_schema), ident(vector_table)),
            source_key=ident(source_key),
            vector_key=ident(vector_source_key),
            stale=stale_expression,
            deleted=deletion_expression,
        )
        try:
            await conn.rollback()
            await conn.execute("SET TRANSACTION READ ONLY")
            await conn.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(timeout_seconds * 1000),),
            )
            cursor = await conn.execute(
                statement,
                (source_schema, source_table, vector_schema, vector_table),
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError("Governance observation returned no aggregate row")
            return dict(row)
        finally:
            await conn.rollback()

    async def close(self) -> None:
        if self._conn and not self._conn.closed:
            await self._conn.close()
            self._conn = None

    async def test_connection_with_latency(self) -> tuple[bool, int]:
        start = time.monotonic()
        ok = await self.test_connection()
        ms = int((time.monotonic() - start) * 1000)
        return ok, ms
