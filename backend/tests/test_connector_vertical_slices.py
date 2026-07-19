import sqlite3
import ssl
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.connectors.duckdb import DuckDBConnector
from app.connectors.mysql import MySQLConnector
from app.connectors.sqlite import SQLiteConnector
from app.connectors.sqlserver import SQLServerConnector
from app.services.profiler import ProfilerService


@pytest.mark.asyncio
async def test_duckdb_discover_and_profile_vertical_slice(tmp_path):
    import duckdb

    database_path = tmp_path / "analytics.duckdb"
    setup = duckdb.connect(str(database_path))
    setup.execute(
        "CREATE TABLE main.orders ("
        'id INTEGER, amount DOUBLE, status VARCHAR, "order total" DOUBLE, '
        "created_at TIMESTAMP)"
    )
    setup.execute(
        "INSERT INTO main.orders VALUES "
        "(1, 12.5, 'paid', 20, TIMESTAMP '2026-07-19 10:00:00'), "
        "(2, 0, '', 10, TIMESTAMP '2026-07-19 11:00:00'), "
        "(3, NULL, NULL, NULL, TIMESTAMP '2026-07-19 12:00:00')"
    )
    setup.close()

    connector = DuckDBConnector({"path": str(database_path)})
    try:
        schemas = await connector.discover_schemas()
        main = next(schema for schema in schemas if schema.name == "main")
        assert [(table.name, table.estimated_rows) for table in main.tables] == [
            ("orders", 3)
        ]

        result = await ProfilerService().profile(
            connector,
            "main",
            "orders",
            freshness_column="created_at",
        )

        assert result.error is None
        assert result.row_count == 3
        assert result.column_metrics["amount"]["null_rate"] == pytest.approx(1 / 3)
        assert result.column_metrics["amount"]["mean"] == pytest.approx(6.25)
        assert result.column_metrics["order total"]["mean"] == pytest.approx(15)
        assert result.column_metrics["status"]["empty_rate"] == pytest.approx(1 / 2)
        assert result.freshness_seconds is not None

        monitor_result = await connector.execute_monitor_query(
            "SELECT COUNT(*) AS violations FROM main.orders WHERE amount IS NULL",
            timeout_seconds=2,
        )
        assert monitor_result == {"violations": 1}
        with pytest.raises(duckdb.Error):
            await connector.execute_profile_query("DELETE FROM main.orders")
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_sqlite_discover_and_profile_vertical_slice(tmp_path):
    database_path = tmp_path / "application.sqlite"
    setup = sqlite3.connect(database_path)
    setup.execute(
        "CREATE TABLE events ("
        'id INTEGER, amount REAL, status TEXT, "order total" REAL, '
        "created_at TIMESTAMP)"
    )
    setup.executemany(
        "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
        [
            (1, 12.5, "paid", 20, "2026-07-19 10:00:00"),
            (2, 0, "", 10, "2026-07-19 11:00:00"),
            (3, None, None, None, "2026-07-19 12:00:00"),
        ],
    )
    setup.commit()
    setup.close()

    connector = SQLiteConnector({"path": str(database_path)})
    try:
        schemas = await connector.discover_schemas()
        assert [(table.name, table.estimated_rows) for table in schemas[0].tables] == [
            ("events", None)
        ]

        result = await ProfilerService().profile(
            connector,
            "main",
            "events",
            freshness_column="created_at",
        )

        assert result.error is None
        assert result.row_count == 3
        assert result.column_metrics["amount"]["null_rate"] == pytest.approx(1 / 3)
        assert result.column_metrics["amount"]["mean"] == pytest.approx(6.25)
        assert result.column_metrics["order total"]["mean"] == pytest.approx(15)
        assert "stddev" not in result.column_metrics["amount"]
        assert result.column_metrics["status"]["empty_rate"] == pytest.approx(1 / 2)
        assert result.freshness_seconds is not None

        monitor_result = await connector.execute_monitor_query(
            "SELECT COUNT(*) AS violations FROM main.events WHERE amount IS NULL",
            timeout_seconds=2,
        )
        assert monitor_result == {"violations": 1}
        with pytest.raises(sqlite3.OperationalError):
            await connector.execute_profile_query("DELETE FROM main.events")
    finally:
        await connector.close()


@pytest.mark.asyncio
async def test_mysql_scalar_execution_imports_dict_cursor_before_use(monkeypatch):
    dict_cursor = object()

    class FakeCursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, query):
            assert query == "SELECT COUNT(*) AS violations FROM orders"

        async def fetchone(self):
            return {"violations": 2}

    class FakeConnection:
        def cursor(self, cursor_type):
            assert cursor_type is dict_cursor
            return FakeCursor()

    class FakeAcquire:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, *_args):
            return None

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    monkeypatch.setitem(sys.modules, "aiomysql", SimpleNamespace(DictCursor=dict_cursor))
    connector = MySQLConnector({"host": "db", "database": "analytics"})
    connector._pool = FakePool()

    result = await connector.execute_profile_query(
        "SELECT COUNT(*) AS violations FROM orders"
    )

    assert result == {"violations": 2}


def test_mysql_declares_only_the_tested_core_profile_dialect():
    assert MySQLConnector.profile_dialect == "mysql"


@pytest.mark.asyncio
async def test_mysql_requires_verified_tls_by_default(monkeypatch):
    captured = {}

    async def create_pool(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setitem(
        sys.modules,
        "aiomysql",
        SimpleNamespace(create_pool=create_pool),
    )
    connector = MySQLConnector(
        {"host": "mysql.example.com", "database": "analytics"}
    )

    await connector._get_pool()

    context = captured["ssl"]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_mysql_tls_can_only_be_disabled_explicitly():
    assert MySQLConnector({"tls_mode": "disabled"})._ssl_context() is None
    with pytest.raises(ValueError, match="tls_mode"):
        MySQLConnector({"tls_mode": "preferred"})._ssl_context()


@pytest.mark.asyncio
async def test_mysql_schema_to_core_profile_contract(monkeypatch):
    dict_cursor = object()
    executed = []

    class FakeCursor:
        def __init__(self, dictionary=False):
            self.dictionary = dictionary

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, query, params=None):
            executed.append((query, params))

        async def fetchall(self):
            return [
                ("id", "int", "NO"),
                ("amount", "decimal(12,2)", "YES"),
                ("status", "varchar(32)", "YES"),
                ("created_at", "datetime", "YES"),
            ]

        async def fetchone(self):
            assert self.dictionary is True
            return {
                "_row_count": 3,
                "null_rate_id": 0.0,
                "distinct_count_id": 3,
                "uniqueness_ratio_id": 1.0,
                "min_id": 1,
                "max_id": 3,
                "mean_id": 2.0,
                "stddev_id": 0.816,
                "zero_rate_id": 0.0,
                "negative_rate_id": 0.0,
                "null_rate_amount": 1 / 3,
                "distinct_count_amount": 2,
                "uniqueness_ratio_amount": 2 / 3,
                "min_amount": 0,
                "max_amount": 12.5,
                "mean_amount": 6.25,
                "stddev_amount": 6.25,
                "zero_rate_amount": 0.5,
                "negative_rate_amount": 0.0,
                "null_rate_status": 0.0,
                "distinct_count_status": 2,
                "uniqueness_ratio_status": 2 / 3,
                "min_len_status": 0,
                "max_len_status": 4,
                "avg_len_status": 2.0,
                "empty_rate_status": 1 / 3,
                "null_rate_created_at": 0.0,
                "distinct_count_created_at": 3,
                "uniqueness_ratio_created_at": 1.0,
                "min_created_at": "2026-07-19 10:00:00",
                "max_created_at": "2026-07-19 12:00:00",
                "range_seconds_created_at": 7200,
                "_freshness_seconds": 3600,
            }

    class FakeConnection:
        def cursor(self, cursor_type=None):
            return FakeCursor(dictionary=cursor_type is dict_cursor)

    class FakeAcquire:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, *_args):
            return None

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    monkeypatch.setitem(sys.modules, "aiomysql", SimpleNamespace(DictCursor=dict_cursor))
    connector = MySQLConnector({"host": "db", "database": "analytics"})
    connector._pool = FakePool()

    result = await ProfilerService().profile(
        connector,
        "analytics",
        "orders",
        freshness_column="created_at",
    )

    assert result.error is None
    assert result.row_count == 3
    assert result.column_metrics["amount"]["mean"] == 6.25
    assert result.column_metrics["status"]["empty_rate"] == pytest.approx(1 / 3)
    profile_query = executed[-1][0]
    assert "FROM `analytics`.`orders`" in profile_query
    assert "STDDEV_POP(`amount`)" in profile_query
    assert "PERCENTILE_CONT" not in profile_query

    ddl = await connector.get_table_ddl("analytics`prod", "order`events")
    assert ddl.startswith("CREATE TABLE `analytics``prod`.`order``events`")


@pytest.mark.asyncio
async def test_mysql_container_connection_discovery_schema_and_profile():
    connector = MySQLConnector(
        {
            "host": "127.0.0.1",
            "port": 3307,
            "database": "datawatch_connector_test",
            "username": "datawatch",
            "password": "datawatch",
            "tls_mode": "disabled",  # isolated local conformance service only
        }
    )
    if not await connector.test_connection():
        await connector.close()
        pytest.skip(
            "MySQL test service unavailable; run docker compose -f "
            "docker-compose.test-dbs.yml up -d test-mysql"
        )

    try:
        schemas = await connector.discover_schemas()
        database = next(
            schema for schema in schemas if schema.name == "datawatch_connector_test"
        )
        assert any(table.name == "orders" for table in database.tables)

        ddl = await connector.get_table_ddl("datawatch_connector_test", "orders")
        assert "`amount` decimal(12,2) NULL" in ddl

        result = await ProfilerService().profile(
            connector,
            "datawatch_connector_test",
            "orders",
            freshness_column="created_at",
        )
        assert result.error is None
        assert result.row_count == 3
        assert result.column_metrics["amount"]["mean"] == pytest.approx(6.25)
        assert result.column_metrics["status"]["empty_rate"] == pytest.approx(1 / 2)
        assert result.freshness_seconds is not None
    finally:
        await connector.close()


def test_sqlserver_dsn_escapes_values_and_enforces_verified_tls():
    connector = SQLServerConnector(
        {
            "host": "db};Encrypt=no;SERVER=attacker",
            "database": "analytics};PWD=hijack",
            "username": "monitor};UID=admin",
            "password": "secret};TrustServerCertificate=yes",
        }
    )

    dsn = connector._connection_string()

    assert connector._odbc_value("a};PWD=hijack") == "{a}};PWD=hijack}"
    assert "SERVER={db}};Encrypt=no;SERVER=attacker,1433}" in dsn
    assert "DATABASE={analytics}};PWD=hijack}" in dsn
    assert "PWD={secret}};TrustServerCertificate=yes}" in dsn
    assert dsn.endswith(";Encrypt=yes;TrustServerCertificate=no")


def test_backend_image_packages_microsoft_odbc_driver_18():
    backend = Path(__file__).parents[1]
    for filename in ("Dockerfile", "Dockerfile.api", "Dockerfile.worker"):
        dockerfile = (backend / filename).read_text()
        assert "FROM python:3.12-slim-bookworm" in dockerfile
        assert (
            "packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb"
            in dockerfile
        )
        assert (
            "ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18"
            in dockerfile
        )
        assert "unixodbc-dev" in dockerfile
