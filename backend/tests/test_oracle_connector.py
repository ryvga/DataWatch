import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.connectors.base import ConnectorConfigurationError
from app.connectors.factory import ConnectorFactory
from app.connectors.oracle import OracleConnector
from app.services.profiler import ColumnInfo, ProfilerService


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.description = []
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.connection.cursor_closes += 1

    async def execute(self, statement, **parameters):
        self.connection.executions.append((statement, parameters))
        normalized = " ".join(statement.split()).upper()
        if self.connection.raise_on_profile and normalized.startswith("SELECT COUNT(*)"):
            raise RuntimeError("driver failure includes top-secret")
        if "FROM ALL_TABLES" in normalized:
            self.rows = [("ORDERS", 42), ('A"B', None)]
        elif "FROM ALL_TAB_COLUMNS" in normalized:
            self.rows = [
                ("ID", "NUMBER", 22, None, 10, 0, "N"),
                ("AMOUNT", "NUMBER", 22, None, 12, 2, "Y"),
                ("CREATED_AT", "TIMESTAMP WITH TIME ZONE", 13, None, None, 6, "N"),
                ('NOTE"TEXT', "VARCHAR2", 200, 100, None, None, "Y"),
                ("PAYLOAD", "CLOB", 4000, None, None, None, "Y"),
            ]
        elif normalized.startswith("SELECT COUNT(*)"):
            self.description = [
                ("_row_count",),
                ("_freshness_seconds",),
                ("null_rate_AMOUNT",),
                ("mean_AMOUNT",),
            ]
            self.rows = [(3, 60, 1 / 3, 12.5)]
        else:
            self.rows = [(1,)] if normalized == "SELECT 1 FROM DUAL" else []
        return self

    async def fetchone(self):
        return self.rows[0] if self.rows else None

    async def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self):
        self.call_timeout = None
        self.executions = []
        self.rollbacks = 0
        self.closes = 0
        self.cursor_closes = 0
        self.cancels = 0
        self.raise_on_profile = False

    def cursor(self):
        return FakeCursor(self)

    async def rollback(self):
        self.rollbacks += 1

    async def close(self):
        self.closes += 1

    def cancel(self):
        self.cancels += 1


@pytest.fixture
def fake_oracledb(monkeypatch):
    connection = FakeConnection()
    captured = {}

    class ConnectParams:
        def __init__(self, **kwargs):
            captured["params"] = kwargs

    async def connect_async(**kwargs):
        captured["connect"] = kwargs
        return connection

    module = SimpleNamespace(
        is_thin_mode=lambda: True,
        ConnectParams=ConnectParams,
        connect_async=connect_async,
    )
    monkeypatch.setitem(sys.modules, "oracledb", module)
    return connection, captured, module


def oracle_config(**overrides):
    config = {
        "host": "oracle.example.com",
        "port": 1521,
        "service_name": "FREEPDB1",
        "username": "panopta_monitor",
        "password": "top-secret",
        "schema": "PANOPTA_MONITOR",
        "tls_mode": "verify_identity",
        "wallet_location": "/run/secrets/oracle-wallet",
        "wallet_password": "wallet-secret",
        "connect_timeout_seconds": 12,
        "call_timeout_ms": 45000,
    }
    config.update(overrides)
    return config


@pytest.mark.asyncio
async def test_oracle_thin_tls_connection_is_bounded_and_secret_safe(fake_oracledb, caplog):
    connection, captured, _ = fake_oracledb
    connector = OracleConnector(oracle_config())

    assert await connector.test_connection() is True
    assert captured["params"] == {
        "host": "oracle.example.com",
        "port": 1521,
        "service_name": "FREEPDB1",
        "protocol": "tcps",
        "ssl_server_dn_match": True,
        "tcp_connect_timeout": 12,
        "wallet_location": "/run/secrets/oracle-wallet",
        "wallet_password": "wallet-secret",
    }
    assert captured["connect"]["user"] == "panopta_monitor"
    assert captured["connect"]["password"] == "top-secret"
    assert connection.call_timeout == 45000

    await connector.close()
    assert connection.closes == 1
    assert "top-secret" not in caplog.text
    assert "wallet-secret" not in caplog.text


@pytest.mark.asyncio
async def test_oracle_scoped_discovery_deterministic_ddl_and_bound_catalogue(fake_oracledb):
    connection, _, _ = fake_oracledb
    connector = OracleConnector(oracle_config())

    schemas = await connector.discover_schemas()
    assert [schema.name for schema in schemas] == ["PANOPTA_MONITOR"]
    assert [(table.name, table.estimated_rows) for table in schemas[0].tables] == [
        ("ORDERS", 42),
        ('A"B', None),
    ]
    ddl, names = await connector.get_table_schema("PANOPTA_MONITOR", 'A"B')
    assert ddl.startswith('CREATE TABLE "PANOPTA_MONITOR"."A""B"')
    assert '"NOTE""TEXT" VARCHAR2(100) NULL' in ddl
    assert '"AMOUNT" NUMBER(12,2) NULL' in ddl
    assert names == {"ID", "AMOUNT", "CREATED_AT", 'NOTE"TEXT', "PAYLOAD"}

    catalogue_calls = [item for item in connection.executions if "ALL_TAB" in item[0]]
    assert catalogue_calls[0][1] == {"owner": "PANOPTA_MONITOR"}
    assert catalogue_calls[1][1] == {
        "owner": "PANOPTA_MONITOR",
        "table_name": 'A"B',
    }
    assert 'A"B' not in catalogue_calls[1][0]
    with pytest.raises(ConnectorConfigurationError, match="configured schema scope"):
        await connector.get_table_ddl("OTHER", "ORDERS")


def test_oracle_profiler_query_is_native_single_scan_and_handles_lobs():
    query = ProfilerService().build_profile_query(
        "PANOPTA_MONITOR",
        'ORD"ERS',
        [
            ColumnInfo("AMOUNT", "NUMBER(12,2)"),
            ColumnInfo("CREATED_AT", "TIMESTAMP WITH TIME ZONE"),
            ColumnInfo("NOTE", "VARCHAR2(100)"),
            ColumnInfo("PAYLOAD", "CLOB"),
        ],
        "CREATED_AT",
        dialect="oracle",
    )

    assert query.count("\nFROM ") == 1
    assert 'FROM "PANOPTA_MONITOR"."ORD""ERS"' in query
    assert 'COUNT(*) AS "_row_count"' in query
    assert "SYSTIMESTAMP" in query
    assert "BINARY_DOUBLE" in query
    assert "DBMS_LOB.GETLENGTH" in query
    assert 'COUNT(DISTINCT "PAYLOAD")' not in query
    assert "::" not in query
    assert "PERCENTILE_CONT" not in query
    assert " = ''" not in query


@pytest.mark.asyncio
async def test_oracle_profile_runs_read_only_rolls_back_and_parses(fake_oracledb):
    connection, _, _ = fake_oracledb
    connector = OracleConnector(oracle_config())

    result = await ProfilerService().profile(
        connector, "PANOPTA_MONITOR", "ORDERS", "CREATED_AT"
    )

    assert result.error is None
    assert result.row_count == 3
    assert result.freshness_seconds == 60
    assert result.column_metrics["AMOUNT"]["mean"] == 12.5
    statements = [" ".join(statement.split()) for statement, _ in connection.executions]
    assert statements.count("SET TRANSACTION READ ONLY") == 1
    profile_selects = [statement for statement in statements if statement.startswith("SELECT COUNT(*)")]
    assert len(profile_selects) == 1
    assert connection.rollbacks == 2


@pytest.mark.asyncio
async def test_oracle_profile_failure_still_rolls_back_and_rejects_writes(fake_oracledb):
    connection, _, _ = fake_oracledb
    connector = OracleConnector(oracle_config())
    await connector._get_conn()
    connection.raise_on_profile = True

    with pytest.raises(RuntimeError):
        await connector.execute_profile_query('SELECT COUNT(*) AS "_row_count" FROM "X"."Y"')
    assert connection.rollbacks == 2
    assert connection.cancels == 1
    assert connection.closes == 1
    with pytest.raises(ConnectorConfigurationError, match="one SELECT"):
        await connector.execute_profile_query('DELETE FROM "X"."Y"')


@pytest.mark.asyncio
async def test_oracle_rejects_thick_mode_and_invalid_bounds(fake_oracledb):
    _, _, module = fake_oracledb
    module.is_thin_mode = lambda: False
    connector = OracleConnector(oracle_config())
    with pytest.raises(ConnectorConfigurationError, match="thin mode"):
        await connector._get_conn()

    module.is_thin_mode = lambda: True
    connector = OracleConnector(oracle_config(call_timeout_ms=999))
    with pytest.raises(ConnectorConfigurationError, match="call_timeout_ms"):
        await connector._get_conn()


@pytest.mark.asyncio
async def test_oracle_production_wallet_is_confined(fake_oracledb, monkeypatch, tmp_path):
    from app.connectors import oracle as oracle_module

    approved = tmp_path / "approved"
    monkeypatch.setattr(oracle_module.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(oracle_module.settings, "ORACLE_WALLET_ROOT", str(approved))
    connector = OracleConnector(oracle_config(wallet_location=str(tmp_path / "outside")))
    with pytest.raises(ConnectorConfigurationError, match="approved wallet root"):
        await connector._get_conn()


def test_oracle_registry_capabilities_are_derived_from_runtime_contract():
    metadata = next(item for item in ConnectorFactory.supported_types() if item["type"] == "oracle")
    assert metadata["readiness"] == "experimental"
    assert metadata["capabilities"] == {
        "connection_test": True,
        "discovery": True,
        "schema": True,
        "profiling": "core",
        "custom_monitors": "none",
        "compiled_monitors": "none",
        "sampling": False,
    }
    fields = {field["name"]: field for field in metadata["fields"]}
    assert fields["password"]["secret"] is True
    assert fields["wallet_password"]["secret"] is True


@pytest.mark.asyncio
async def test_oracle_api_onboarding_worker_profile_and_persisted_retrieval(
    client, auth_headers, db_session, monkeypatch
):
    """Exercise the public API and real worker persistence around the adapter contract."""

    class VerticalConnector:
        profile_dialect = "oracle"

        async def test_connection(self):
            return True

        async def discover_schemas(self):
            from app.connectors.base import SchemaInfo, TableInfo

            return [SchemaInfo(name="PANOPTA_MONITOR", tables=[TableInfo("ORDERS", 3)])]

        async def get_table_ddl(self, schema, table):
            assert (schema, table) == ("PANOPTA_MONITOR", "ORDERS")
            return (
                'CREATE TABLE "PANOPTA_MONITOR"."ORDERS" (\n'
                '  "ID" NUMBER(10,0) NOT NULL,\n'
                '  "CREATED_AT" TIMESTAMP(6) WITH TIME ZONE NOT NULL\n);'
            )

        async def get_table_schema(self, schema, table):
            return await self.get_table_ddl(schema, table), {"ID", "CREATED_AT"}

        async def validate_profile_config(self, schema, table, freshness_column):
            assert (schema, table, freshness_column) == (
                "PANOPTA_MONITOR",
                "ORDERS",
                "CREATED_AT",
            )

        async def execute_profile_query(self, query):
            assert query.count("\nFROM ") == 1
            assert 'FROM "PANOPTA_MONITOR"."ORDERS"' in query
            return {
                "_row_count": 3,
                "_freshness_seconds": 45,
                "null_rate_ID": 0,
                "distinct_count_ID": 3,
                "uniqueness_ratio_ID": 1,
            }

        async def close(self):
            return None

    class AsyncRedis:
        async def setex(self, *_args):
            return True

        async def aclose(self):
            return None

    async def allow(*_args):
        return None

    async def redis_client():
        return AsyncRedis()

    monkeypatch.setattr(
        "app.connectors.factory.ConnectorFactory.create",
        staticmethod(lambda source_type, config: VerticalConnector()),
    )
    monkeypatch.setattr("app.routers.sources._enforce_connection_rate_limit", allow)
    monkeypatch.setattr("app.routers.sources.enforce_source_target_policy", allow)
    monkeypatch.setattr("app.routers.sources._redis", redis_client)

    source_response = await client.post(
        "/api/v1/sources",
        headers=auth_headers,
        json={
            "name": "Oracle PFE",
            "type": "oracle",
            "connection_config": oracle_config(),
        },
    )
    assert source_response.status_code == 201, source_response.text
    source_id = source_response.json()["id"]

    discovery = await client.post(
        f"/api/v1/sources/{source_id}/discover", headers=auth_headers
    )
    assert discovery.status_code == 200, discovery.text
    assert discovery.json()["schemas"][0] == {
        "name": "PANOPTA_MONITOR",
        "tables": [{"name": "ORDERS", "estimated_rows": 3}],
    }

    with patch("app.scheduler.add_table_job"), patch(
        "app.tasks.profile_table"
    ) as queued_profile, patch("app.tasks.bootstrap_table_autopilot") as autopilot:
        queued_profile.delay = MagicMock()
        autopilot.delay = MagicMock()
        table_response = await client.post(
            "/api/v1/tables",
            headers=auth_headers,
            json={
                "source_id": source_id,
                "schema_name": "PANOPTA_MONITOR",
                "table_name": "ORDERS",
                "freshness_column": "CREATED_AT",
            },
        )
    assert table_response.status_code == 201, table_response.text
    table_id = table_response.json()["id"]
    queued_profile.delay.assert_called_once_with(table_id)

    class SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args):
            return False

    sync_redis = SimpleNamespace(close=lambda: None)
    with patch("app.database.AsyncSessionLocal", return_value=SessionContext()), patch(
        "redis.from_url", return_value=sync_redis
    ), patch("app.services.plans.check_and_increment_rate", return_value=True), patch(
        "app.tasks.run_anomaly_checks"
    ) as anomaly, patch("app.tasks.run_custom_monitors") as custom, patch(
        "app.tasks.run_dsl_monitors"
    ) as dsl:
        from app.tasks import _profile_table_async

        result = await _profile_table_async(table_id)

    assert result["status"] == "ok"
    assert result["row_count"] == 3
    anomaly.delay.assert_called_once()
    custom.delay.assert_called_once()
    dsl.delay.assert_called_once()

    retrieved = await client.get(f"/api/v1/tables/{table_id}", headers=auth_headers)
    assert retrieved.status_code == 200, retrieved.text
    latest = retrieved.json()["latest_profile"]
    assert latest["row_count"] == 3
    assert latest["freshness_seconds"] == 45
    assert latest["error"] is None


@pytest.mark.asyncio
async def test_oracle_database_free_container_vertical():
    if os.environ.get("RUN_ORACLE_CONTAINER_TESTS", "").lower() not in {
        "1",
        "true",
        "yes",
    }:
        pytest.skip(
            "set RUN_ORACLE_CONTAINER_TESTS=1 after starting the optional test-oracle profile"
        )

    connector = OracleConnector(
        {
            "host": "127.0.0.1",
            "port": 1522,
            "service_name": "FREEPDB1",
            "username": "DATAWATCH",
            "password": "DataWatch-Oracle-2026",
            "schema": "DATAWATCH",
            "tls_mode": "disabled",
            "connect_timeout_seconds": 30,
            "call_timeout_ms": 120000,
        }
    )
    conn = await connector._get_conn()
    try:
        with conn.cursor() as cursor:
            try:
                await cursor.execute("DROP TABLE PANOPTA_CONNECTOR_TEST PURGE")
            except Exception:
                pass
            await cursor.execute(
                "CREATE TABLE PANOPTA_CONNECTOR_TEST ("
                "ID NUMBER(10,0) NOT NULL, AMOUNT NUMBER(12,2), "
                "STATUS VARCHAR2(20), CREATED_AT TIMESTAMP WITH TIME ZONE NOT NULL)"
            )
            await cursor.executemany(
                "INSERT INTO PANOPTA_CONNECTOR_TEST VALUES (:1, :2, :3, :4)",
                [
                    (1, 10.5, "paid", datetime(2026, 8, 21, 10, tzinfo=timezone.utc)),
                    (2, None, None, datetime(2026, 8, 21, 11, tzinfo=timezone.utc)),
                    (3, 0, "paid", datetime(2026, 8, 21, 12, tzinfo=timezone.utc)),
                ],
            )
        await conn.commit()

        assert await connector.test_connection() is True
        schemas = await connector.discover_schemas()
        schema = next(item for item in schemas if item.name == "DATAWATCH")
        assert "PANOPTA_CONNECTOR_TEST" in {table.name for table in schema.tables}
        ddl = await connector.get_table_ddl("DATAWATCH", "PANOPTA_CONNECTOR_TEST")
        assert ddl.startswith('CREATE TABLE "DATAWATCH"."PANOPTA_CONNECTOR_TEST"')
        result = await ProfilerService().profile(
            connector,
            "DATAWATCH",
            "PANOPTA_CONNECTOR_TEST",
            "CREATED_AT",
        )
        assert result.error is None
        assert result.row_count == 3
        assert result.column_metrics["AMOUNT"]["null_rate"] == pytest.approx(1 / 3)
    finally:
        try:
            with conn.cursor() as cursor:
                await cursor.execute("DROP TABLE PANOPTA_CONNECTOR_TEST PURGE")
            await conn.commit()
        finally:
            await connector.close()
