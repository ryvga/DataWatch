import asyncio
import os
from types import SimpleNamespace

import pytest
from sqlglot import parse_one

from app.connectors.clickhouse import ClickHouseConnector
from app.connectors.databricks import DatabricksConnector
from app.connectors.redshift import RedshiftConnector
from app.connectors.trino import TrinoConnector
from app.services.profiler import ColumnInfo, ProfilerService


@pytest.mark.parametrize(
    ("dialect", "parser", "expected"),
    [
        (
            "redshift",
            "redshift",
            ["DATEDIFF(second", "STDDEV_POP(CAST", "CAST(\"status\" AS VARCHAR)"],
        ),
        (
            "clickhouse",
            "clickhouse",
            ["dateDiff('second'", "stddevPop(toFloat64", "lengthUTF8(toString"],
        ),
        (
            "databricks",
            "databricks",
            ["TIMESTAMPDIFF(SECOND", "STDDEV_POP(CAST", "CAST(`status` AS STRING)"],
        ),
        (
            "trino",
            "trino",
            ["date_diff('second'", "STDDEV_POP(CAST", "CAST(\"status\" AS VARCHAR)"],
        ),
    ],
)
def test_warehouse_profile_planners_emit_native_core_sql(dialect, parser, expected):
    query = ProfilerService().build_profile_query(
        "analytics",
        "order events",
        [
            ColumnInfo("amount", "DECIMAL(12,2)"),
            ColumnInfo("status", "VARCHAR"),
            ColumnInfo("created_at", "TIMESTAMP"),
        ],
        "created_at",
        dialect=dialect,
    )

    assert all(fragment in query for fragment in expected)
    assert "PERCENTILE_CONT" not in query
    assert parse_one(query, read=parser).key == "select"


def test_warehouse_planners_quote_adversarial_discovered_identifiers():
    service = ProfilerService()
    redshift = service.build_profile_query(
        'ops"prod', "order events", [ColumnInfo('amount"gross', "INTEGER")], None, "redshift"
    )
    clickhouse = service.build_profile_query(
        "ops`prod", "order events", [ColumnInfo("amount`gross", "Int64")], None, "clickhouse"
    )
    databricks = service.build_profile_query(
        "ops`prod", "order events", [ColumnInfo("amount`gross", "BIGINT")], None, "databricks"
    )
    trino = service.build_profile_query(
        'ops"prod', "order events", [ColumnInfo('amount"gross', "BIGINT")], None, "trino"
    )

    assert 'FROM "ops""prod"."order events"' in redshift
    assert '`amount``gross`' in clickhouse
    assert 'FROM `ops``prod`.`order events`' in databricks
    assert '"amount""gross"' in trino


class _AsyncRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def __aiter__(self):
        self._iterator = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class _RedshiftConnection:
    closed = False

    def __init__(self):
        self.calls = []

    async def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))
        if "svv_tables" in statement:
            return _AsyncRows([{"schemaname": "safe", "tablename": "events"}])
        if "information_schema.columns" in statement:
            return _AsyncRows(
                [{"column_name": 'event"id', "data_type": "bigint", "is_nullable": "NO"}]
            )
        return _AsyncRows([{"_row_count": 4}])

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_redshift_scope_is_bound_and_ddl_is_quoted():
    conn = _RedshiftConnection()
    connector = RedshiftConnector(
        {
            "host": "redshift.example",
            "database": "analytics",
            "username": "reader",
            "password": "secret",
            "schema": "safe",
        }
    )
    connector._conn = conn

    schemas = await connector.discover_schemas()
    ddl = await connector.get_table_ddl("safe", "events")
    profile = await connector.execute_profile_query("SELECT COUNT(*) AS _row_count")

    assert schemas[0].name == "safe"
    assert conn.calls[0][1] == ("safe",)
    assert conn.calls[1][1] == ("safe", "events")
    assert '"event""id" bigint NOT NULL' in ddl
    assert profile == {"_row_count": 4}
    with pytest.raises(ValueError, match="restricted"):
        await connector.get_table_ddl("other", "events")


class _ClickHouseClient:
    def __init__(self):
        self.calls = []

    async def query(self, statement, *, parameters=None, settings=None):
        self.calls.append((statement, parameters, settings))
        if "system.tables" in statement:
            return SimpleNamespace(
                result_rows=[("analytics", "events", 7)], column_names=[]
            )
        if "system.columns" in statement:
            return SimpleNamespace(
                result_rows=[("event`id", "Int64", 1)], column_names=[]
            )
        return SimpleNamespace(result_rows=[(7,)], column_names=["_row_count"])


@pytest.mark.asyncio
async def test_clickhouse_scope_profile_settings_and_quoted_ddl():
    client = _ClickHouseClient()
    connector = ClickHouseConnector({"host": "clickhouse.example", "database": "analytics"})
    connector._client = client

    schemas = await connector.discover_schemas()
    ddl = await connector.get_table_ddl("analytics", "events")
    profile = await connector.execute_profile_query("SELECT count() AS _row_count")

    assert schemas[0].tables[0].estimated_rows == 7
    assert client.calls[0][1] == {"database": "analytics"}
    assert client.calls[1][1] == {"db": "analytics", "tbl": "events"}
    assert client.calls[2][2] == {"readonly": 2, "max_execution_time": 120}
    assert "`event``id` Int64" in ddl
    assert profile == {"_row_count": 7}


class _Cursor:
    def __init__(self, response, calls):
        self._rows, columns = response
        self.description = [(column,) for column in columns]
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, statement, parameters=None):
        self._calls.append((statement, parameters))

    def fetchall(self):
        return self._rows


class _SyncConnection:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def cursor(self):
        return _Cursor(self._responses.pop(0), self.calls)


@pytest.mark.asyncio
async def test_databricks_catalog_and_schema_are_bound_not_interpolated():
    conn = _SyncConnection(
        [
            ([("safe", "events", None)], ["table_schema", "table_name", "est_rows"]),
            ([("event`id", "BIGINT", "NO")], ["column_name", "data_type", "is_nullable"]),
        ]
    )
    connector = DatabricksConnector(
        {
            "server_hostname": "dbc.example",
            "http_path": "/sql/1",
            "access_token": "secret",
            "catalog": "main'; DROP TABLE audit;--",
            "schema": "safe",
        }
    )
    connector._conn = conn

    await connector.discover_schemas()
    ddl = await connector.get_table_ddl("safe", "events")

    assert "DROP TABLE" not in conn.calls[0][0]
    assert conn.calls[0][1] == ["main'; DROP TABLE audit;--", "safe"]
    assert conn.calls[1][1] == ["main'; DROP TABLE audit;--", "safe", "events"]
    assert "`event``id` BIGINT NOT NULL" in ddl


@pytest.mark.asyncio
async def test_trino_schema_and_table_are_bound_not_interpolated():
    conn = _SyncConnection(
        [
            ([("safe", "events")], ["table_schema", "table_name"]),
            ([("event\"id", "bigint", "NO")], ["column_name", "data_type", "is_nullable"]),
        ]
    )
    connector = TrinoConnector(
        {"host": "trino.example", "catalog": "hive", "schema": "safe"}
    )
    connector._conn = conn

    await connector.discover_schemas()
    ddl = await connector.get_table_ddl("safe", "events")

    assert conn.calls[0][1] == ("safe",)
    assert conn.calls[1][1] == ("safe", "events")
    assert '"event""id" bigint NOT NULL' in ddl
    with pytest.raises(ValueError, match="restricted"):
        await connector.get_table_ddl("other", "events")


def _warehouse_container_lane_enabled() -> bool:
    return os.environ.get("RUN_WAREHOUSE_CONTAINER_TESTS", "").lower() in {
        "1",
        "true",
        "yes",
    }


@pytest.mark.asyncio
async def test_clickhouse_container_vertical():
    if not _warehouse_container_lane_enabled():
        pytest.skip("set RUN_WAREHOUSE_CONTAINER_TESTS=1 for live warehouse conformance")
    connector = ClickHouseConnector(
        {
            "host": "127.0.0.1",
            "port": 8124,
            "database": "analytics",
            "username": "datawatch",
            "password": "datawatch",
        }
    )
    client = await connector._get_client()
    try:
        await client.command("DROP TABLE IF EXISTS analytics.events")
        await client.command(
            "CREATE TABLE analytics.events "
            "(id Int64, amount Float64, status String, created_at DateTime) ENGINE = Memory"
        )
        await client.command(
            "INSERT INTO analytics.events VALUES "
            "(1, 10.5, 'ok', now()), (2, -1.0, '', now())"
        )

        assert await connector.test_connection() is True
        schemas = await connector.discover_schemas()
        profile = await ProfilerService().profile(
            connector, "analytics", "events", "created_at"
        )

        assert any(table.name == "events" for table in schemas[0].tables)
        assert profile.error is None
        assert profile.row_count == 2
        assert profile.column_metrics["amount"]["negative_rate"] == pytest.approx(0.5)
    finally:
        await client.command("DROP TABLE IF EXISTS analytics.events")
        await connector.close()


@pytest.mark.asyncio
async def test_trino_container_vertical():
    if not _warehouse_container_lane_enabled():
        pytest.skip("set RUN_WAREHOUSE_CONTAINER_TESTS=1 for live warehouse conformance")
    import trino

    config = {
        "host": "127.0.0.1",
        "port": 8081,
        "user": "datawatch",
        "catalog": "memory",
        "schema": "analytics",
    }

    def _seed():
        conn = trino.dbapi.connect(**config)
        with conn.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS memory.analytics")
            cursor.execute("DROP TABLE IF EXISTS memory.analytics.events")
            cursor.execute(
                "CREATE TABLE memory.analytics.events "
                "(id BIGINT, amount DOUBLE, status VARCHAR, created_at TIMESTAMP)"
            )
            cursor.execute(
                "INSERT INTO memory.analytics.events VALUES "
                "(1, 10.5, 'ok', CURRENT_TIMESTAMP), "
                "(2, -1.0, '', CURRENT_TIMESTAMP)"
            )
        conn.close()

    def _cleanup():
        conn = trino.dbapi.connect(**config)
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS memory.analytics.events")
        conn.close()

    await asyncio.to_thread(_seed)
    connector = TrinoConnector(config)
    try:
        assert await connector.test_connection() is True
        schemas = await connector.discover_schemas()
        profile = await ProfilerService().profile(
            connector, "analytics", "events", "created_at"
        )

        assert any(table.name == "events" for table in schemas[0].tables)
        assert profile.error is None
        assert profile.row_count == 2
        assert profile.column_metrics["amount"]["negative_rate"] == pytest.approx(0.5)
    finally:
        await connector.close()
        await asyncio.to_thread(_cleanup)
