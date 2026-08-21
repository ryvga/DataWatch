import sys
from types import ModuleType

import pytest

from app.connectors.base import ConnectorConfigurationError
from app.connectors.snowflake import SnowflakeConnector
from app.services.profiler import ColumnInfo, ProfilerService


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


class _Connection:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.closed = False

    def is_closed(self):
        return self.closed

    def cursor(self):
        return _Cursor(self._responses.pop(0), self.calls)

    def close(self):
        self.closed = True


def _config(**overrides):
    return {
        "account": "xy12345.eu-west-1",
        "user": "PANOPTA_READER",
        "password": "not-logged",
        "database": "ANALYTICS",
        "warehouse": "PANOPTA_XS",
        "schema": "PUBLIC",
        **overrides,
    }


def test_snowflake_connection_uses_explicit_timeout_and_session_controls(monkeypatch):
    captured = {}
    connector_module = ModuleType("snowflake.connector")

    def _connect(**kwargs):
        captured.update(kwargs)
        return object()

    connector_module.connect = _connect
    snowflake_module = ModuleType("snowflake")
    snowflake_module.connector = connector_module
    monkeypatch.setitem(sys.modules, "snowflake", snowflake_module)
    monkeypatch.setitem(sys.modules, "snowflake.connector", connector_module)

    connector = SnowflakeConnector(_config(query_timeout_seconds=31))
    assert connector._connect_sync() is not None

    assert captured["account"] == "xy12345.eu-west-1"
    assert captured["login_timeout"] == 31
    assert captured["network_timeout"] == 31
    assert captured["socket_timeout"] == 31
    assert captured["client_session_keep_alive"] is False
    assert captured["session_parameters"] == {
        "STATEMENT_TIMEOUT_IN_SECONDS": 31,
        "QUERY_TAG": "panopta-profile",
    }


@pytest.mark.asyncio
async def test_snowflake_scoped_vertical_and_cleanup():
    conn = _Connection(
        [
            ([(1,)], ["1"]),
            ([("PUBLIC", "EVENTS", 12)], ["TABLE_SCHEMA", "TABLE_NAME", "ROW_COUNT"]),
            (
                [("event\"id", "NUMBER", "NO"), ("status", "VARCHAR", "YES")],
                ["COLUMN_NAME", "DATA_TYPE", "IS_NULLABLE"],
            ),
            ([(12, 0.0)], ["_row_count", "null_rate_status"]),
        ]
    )
    connector = SnowflakeConnector(_config())
    connector._conn = conn

    assert await connector.test_connection() is True
    schemas = await connector.discover_schemas()
    ddl = await connector.get_table_ddl("PUBLIC", "EVENTS")
    profile = await connector.execute_profile_query("SELECT COUNT(*) AS _row_count")
    await connector.close()

    assert schemas[0].name == "PUBLIC"
    assert schemas[0].tables[0].estimated_rows == 12
    assert schemas[0].tables[0].name == "EVENTS"
    assert '"event""id" NUMBER NOT NULL' in ddl
    assert profile == {"_row_count": 12, "null_rate_status": 0.0}
    assert conn.calls[1][1] == ("PUBLIC",)
    assert conn.calls[2][1] == ("PUBLIC", "EVENTS")
    assert conn.closed is True
    assert connector._conn is None


@pytest.mark.asyncio
async def test_snowflake_rejects_cross_schema_and_invalid_identifier_before_query():
    conn = _Connection([])
    connector = SnowflakeConnector(_config())
    connector._conn = conn

    with pytest.raises(ValueError, match="restricted"):
        await connector.get_table_ddl("PRIVATE", "EVENTS")
    with pytest.raises(ValueError, match="NUL"):
        await connector.get_table_ddl("PUBLIC", "bad\x00table")

    assert conn.calls == []


@pytest.mark.parametrize("value", [0, 601, "slow"])
def test_snowflake_rejects_invalid_query_timeout(value):
    connector = SnowflakeConnector(_config(query_timeout_seconds=value))

    with pytest.raises(ConnectorConfigurationError, match="query_timeout_seconds"):
        connector._timeout_seconds()


def test_snowflake_profiler_uses_native_core_dialect_and_quoted_assets():
    query = ProfilerService().build_profile_query(
        'PUBLIC"OPS',
        "ORDER EVENTS",
        [
            ColumnInfo('amount"gross', "NUMBER(12,2)"),
            ColumnInfo("status", "VARCHAR"),
            ColumnInfo("created_at", "TIMESTAMP_TZ"),
        ],
        "created_at",
        dialect="snowflake",
    )

    assert 'FROM "PUBLIC""OPS"."ORDER EVENTS"' in query
    assert 'STDDEV_POP(TO_DOUBLE("amount""gross"))' in query
    assert 'COUNT_IF("amount""gross" IS NULL)' in query
    assert 'TO_VARCHAR("status")' in query
    assert "DATEDIFF('second', MAX(\"created_at\"), CURRENT_TIMESTAMP())" in query
    assert "PERCENTILE_CONT" not in query
    assert "::" not in query


@pytest.mark.asyncio
async def test_snowflake_connection_failure_is_secret_free(caplog):
    connector = SnowflakeConnector(_config())

    async def _fail(*_args, **_kwargs):
        raise RuntimeError("driver included not-logged")

    connector._fetch = _fail
    assert await connector.test_connection() is False
    assert "RuntimeError" in caplog.text
    assert "not-logged" not in caplog.text
