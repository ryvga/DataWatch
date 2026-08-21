import asyncio
import logging
import ssl
from typing import Any
from uuid import UUID

from app.connectors.base import BaseConnector, RowScanBudgetExceeded, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)

_SYSTEM_KEYSPACES = {
    "system",
    "system_auth",
    "system_distributed",
    "system_traces",
    "system_schema",
    "system_virtual_schema",
}


class CassandraConnector(BaseConnector):
    """
    Apache Cassandra connector via cassandra-driver.

    cassandra-driver is synchronous, so calls are wrapped with asyncio.to_thread()
    to keep FastAPI/Celery async wrappers from blocking the event loop.
    """

    def __init__(self, config: dict):
        self._config = config
        self._cluster: Any | None = None
        self._session: Any | None = None
        self._connect_lock = asyncio.Lock()

    native_profile_kind = "partition"

    @staticmethod
    def _parse_hosts(hosts: str | list[str]) -> list[str]:
        if isinstance(hosts, str):
            return [host.strip() for host in hosts.split(",") if host.strip()]
        return [str(host).strip() for host in hosts if str(host).strip()]

    def _connect_sync(self):
        if self._session is not None:
            return self._session

        from cassandra.auth import PlainTextAuthProvider
        from cassandra.cluster import Cluster

        c = self._config
        hosts = self._parse_hosts(c["hosts"])
        if not hosts:
            raise ValueError("Cassandra requires at least one contact point")
        auth_provider = None
        username = c.get("username") or c.get("user")
        password = c.get("password")
        if username:
            auth_provider = PlainTextAuthProvider(
                username=username,
                password=password or "",
            )

        ssl_context = self._ssl_context()
        cluster_options = {
            "contact_points": hosts,
            "port": int(c.get("port", 9042)),
            "auth_provider": auth_provider,
            "ssl_context": ssl_context,
        }
        if ssl_context is not None:
            cluster_options["ssl_options"] = {
                "server_hostname": c.get("tls_server_name") or hosts[0],
            }

        self._cluster = Cluster(
            **cluster_options,
        )
        keyspace = c.get("keyspace")
        self._session = self._cluster.connect(keyspace) if keyspace else self._cluster.connect()
        return self._session

    def _ssl_context(self) -> ssl.SSLContext | None:
        mode = str(self._config.get("tls_mode", "verify_identity")).lower()
        if mode == "disabled":
            return None
        if mode != "verify_identity":
            raise ValueError("tls_mode must be 'verify_identity' or 'disabled'")
        context = ssl.create_default_context(cadata=self._config.get("ssl_ca") or None)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        return context

    async def _get_session(self):
        if self._session is not None:
            return self._session
        async with self._connect_lock:
            if self._session is None:
                await asyncio.to_thread(self._connect_sync)
        return self._session

    async def test_connection(self) -> bool:
        try:
            session = await self._get_session()
            await asyncio.to_thread(
                session.execute,
                "SELECT cluster_name FROM system.local",
                timeout=10,
            )
            return bool(self._cluster and self._cluster.metadata.keyspaces)
        except Exception as e:
            logger.warning("Cassandra connection test failed: %s", type(e).__name__)
            return False

    async def discover_schemas(self) -> list[SchemaInfo]:
        await self._get_session()

        def _discover() -> list[SchemaInfo]:
            schemas: list[SchemaInfo] = []
            keyspaces = self._cluster.metadata.keyspaces.items()
            configured_keyspace = self._config.get("keyspace")
            for keyspace_name, keyspace in sorted(keyspaces):
                if keyspace_name in _SYSTEM_KEYSPACES:
                    continue
                if configured_keyspace and keyspace_name != configured_keyspace:
                    continue

                tables = [TableInfo(name=table_name, estimated_rows=None) for table_name in sorted(keyspace.tables)]
                schemas.append(SchemaInfo(name=keyspace_name, tables=tables))
            return schemas

        return await asyncio.to_thread(_discover)

    async def execute_profile_query(self, query: str) -> dict:
        raise NotImplementedError("Cassandra does not execute caller-provided CQL; a typed partition plan is required")

    async def execute_partition_monitor(self, plan) -> dict:
        from app.services.cassandra_monitor import (
            CassandraMonitorPlan,
            evaluate_cassandra_rows,
            render_cassandra_statement,
        )

        if not isinstance(plan, CassandraMonitorPlan):
            raise ValueError("Cassandra monitor plan type is invalid")
        self._validate_scope(plan.relation.schema_name, plan.relation.table_name)
        expected = render_cassandra_statement(
            plan.relation,
            plan.selected_fields,
            plan.partition_keys,
            plan.max_rows_scanned,
        )
        if plan.statement != expected or not 1 <= plan.timeout_seconds <= 120:
            raise ValueError("Cassandra monitor plan contract is invalid")
        session = await self._get_session()

        def _execute() -> list[dict[str, Any]]:
            prepared = session.prepare(plan.statement)
            values = tuple(
                _coerce_partition_value(
                    plan.relation.column(key).data_type,
                    value,
                )
                for key, value in zip(plan.partition_keys, plan.partition_values)
            )
            bound = prepared.bind(values)
            bound.fetch_size = plan.max_rows_scanned + 1
            result = session.execute(bound, timeout=plan.timeout_seconds)
            rows = list(result)
            return [_row_mapping(row, plan.selected_fields) for row in rows]

        rows = await asyncio.to_thread(_execute)
        if len(rows) > plan.max_rows_scanned:
            raise RowScanBudgetExceeded("Cassandra monitor reached maxRowsScanned")
        return evaluate_cassandra_rows(plan, rows)

    async def get_table_ddl(self, schema: str, table: str) -> str:
        await self._get_session()

        def _ddl() -> str:
            table_meta = self._get_table_metadata(schema, table)
            partition_keys = {column.name for column in table_meta.partition_key}
            clustering_keys = {column.name for column in table_meta.clustering_key}

            lines = []
            for column_name, column in table_meta.columns.items():
                lines.append(
                    "  "
                    f"{_quote_identifier(column_name)} {column.cql_type} "
                    f"is_partition_key={str(column_name in partition_keys).lower()} "
                    f"is_clustering_key={str(column_name in clustering_keys).lower()}"
                )

            return (
                f"CREATE TABLE {_quote_identifier(schema)}.{_quote_identifier(table)} (\n" + ",\n".join(lines) + "\n);"
            )

        return await asyncio.to_thread(_ddl)

    async def get_table_schema(
        self,
        schema: str,
        table: str,
    ) -> tuple[str, set[str]]:
        ddl = await self.get_table_ddl(schema, table)
        table_meta = self._get_table_metadata(schema, table)
        return ddl, set(table_meta.columns)

    async def close(self) -> None:
        session = self._session
        cluster = self._cluster
        self._session = None
        self._cluster = None

        def _close() -> None:
            if session is not None:
                session.shutdown()
            if cluster is not None:
                cluster.shutdown()

        await asyncio.to_thread(_close)

    def _get_table_metadata(self, schema: str, table: str):
        self._validate_scope(schema, table)
        keyspaces = self._cluster.metadata.keyspaces
        keyspace = keyspaces.get(schema) or keyspaces.get(schema.lower())
        if keyspace is None:
            raise ValueError(f"Cassandra keyspace not found: {schema}")

        table_meta = keyspace.tables.get(table) or keyspace.tables.get(table.lower())
        if table_meta is None:
            raise ValueError(f"Cassandra table not found: {schema}.{table}")
        return table_meta

    def _validate_scope(self, schema: str, table: str) -> None:
        configured = self._config.get("keyspace")
        if configured and schema != configured:
            raise ValueError("Cassandra operations are restricted to the configured keyspace")
        if not schema or not table or "\x00" in schema or "\x00" in table:
            raise ValueError("Cassandra keyspace or table is invalid")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _coerce_partition_value(data_type: str, value):
    normalized = data_type.lower()
    if normalized in {"uuid", "timeuuid"} and isinstance(value, str):
        return UUID(value)
    return value


def _row_mapping(row, selected_fields: tuple[str, ...]) -> dict[str, Any]:
    if hasattr(row, "_asdict"):
        values = row._asdict()
        return {field: values.get(field) for field in selected_fields}
    if isinstance(row, dict):
        return {field: row.get(field) for field in selected_fields}
    return {field: getattr(row, field) for field in selected_fields}
