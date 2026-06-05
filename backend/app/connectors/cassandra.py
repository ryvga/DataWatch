import asyncio
import logging
import re
from typing import Any

from app.connectors.base import BaseConnector, SchemaInfo, TableInfo

logger = logging.getLogger(__name__)

_SYSTEM_KEYSPACES = {
    "system",
    "system_auth",
    "system_distributed",
    "system_traces",
    "system_schema",
    "system_virtual_schema",
}

_COUNT_STAR_RE = re.compile(
    r"\bselect\s+count\s*\(\s*\*\s*\)\s+from\b",
    re.IGNORECASE | re.DOTALL,
)
_IDENTIFIER_RE = r'(?:[a-zA-Z_][\w]*|"[^"]+")'
_COUNT_QUERY_RE = re.compile(
    r"\bselect\s+count\s*\(\s*\*\s*\)\s+from\s+"
    rf"(?P<table>{_IDENTIFIER_RE}(?:\.{_IDENTIFIER_RE})?)"
    r"(?P<rest>.*)",
    re.IGNORECASE | re.DOTALL,
)


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
        auth_provider = None
        username = c.get("username") or c.get("user")
        password = c.get("password")
        if username:
            auth_provider = PlainTextAuthProvider(
                username=username,
                password=password or "",
            )

        self._cluster = Cluster(
            contact_points=hosts,
            port=int(c.get("port", 9042)),
            auth_provider=auth_provider,
        )
        keyspace = c.get("keyspace")
        self._session = (
            self._cluster.connect(keyspace) if keyspace else self._cluster.connect()
        )
        return self._session

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
            for keyspace_name, keyspace in sorted(keyspaces):
                if keyspace_name in _SYSTEM_KEYSPACES:
                    continue

                tables = [
                    TableInfo(name=table_name, estimated_rows=None)
                    for table_name in sorted(keyspace.tables)
                ]
                schemas.append(SchemaInfo(name=keyspace_name, tables=tables))
            return schemas

        return await asyncio.to_thread(_discover)

    async def execute_profile_query(self, query: str) -> dict:
        session = await self._get_session()
        await self._validate_count_query(query)

        def _execute() -> dict:
            result = session.execute(query, timeout=10)
            row = result.one()
            if row is None:
                return {}
            if hasattr(row, "_asdict"):
                return dict(row._asdict())
            return dict(zip(result.column_names, row))

        return await asyncio.to_thread(_execute)

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
                    f"{column_name} {column.cql_type} "
                    f"is_partition_key={str(column_name in partition_keys).lower()} "
                    f"is_clustering_key={str(column_name in clustering_keys).lower()}"
                )

            return (
                f"CREATE TABLE {schema}.{table} (\n"
                + ",\n".join(lines)
                + "\n);"
            )

        return await asyncio.to_thread(_ddl)

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
        keyspaces = self._cluster.metadata.keyspaces
        keyspace = keyspaces.get(schema) or keyspaces.get(schema.lower())
        if keyspace is None:
            raise ValueError(f"Cassandra keyspace not found: {schema}")

        table_meta = keyspace.tables.get(table) or keyspace.tables.get(table.lower())
        if table_meta is None:
            raise ValueError(f"Cassandra table not found: {schema}.{table}")
        return table_meta

    async def _validate_count_query(self, query: str) -> None:
        normalized_query = query.strip().rstrip(";")
        if _COUNT_STAR_RE.search(normalized_query) is None:
            return

        match = _COUNT_QUERY_RE.search(normalized_query)
        if match is None:
            raise ValueError(
                "Cassandra COUNT(*) queries must be parseable for partition key "
                "safety validation."
            )

        table_ref = match.group("table")
        rest = match.group("rest")
        if "." in table_ref:
            schema, table = table_ref.split(".", 1)
        else:
            schema = self._config.get("keyspace")
            table = table_ref
        schema = _normalize_identifier(schema) if schema else schema
        table = _normalize_identifier(table)

        if not schema:
            raise ValueError(
                "Cassandra COUNT(*) queries require an explicit keyspace and full "
                "partition key filter."
            )
        if not re.search(r"\bwhere\b", rest, re.IGNORECASE):
            raise ValueError(
                "Cassandra COUNT(*) without a partition key filter is not allowed."
            )

        def _partition_keys() -> set[str]:
            table_meta = self._get_table_metadata(schema, table)
            return {column.name.lower() for column in table_meta.partition_key}

        partition_keys = await asyncio.to_thread(_partition_keys)
        filtered_columns = {
            _normalize_identifier(column).lower()
            for column in re.findall(
                rf"\b({_IDENTIFIER_RE})\b\s*(?:=|in\b)", rest, re.IGNORECASE
            )
        }
        if not partition_keys.issubset(filtered_columns):
            raise ValueError(
                "Cassandra COUNT(*) requires filters for every partition key column."
            )


def _normalize_identifier(identifier: str) -> str:
    if identifier.startswith('"') and identifier.endswith('"'):
        return identifier[1:-1]
    return identifier
