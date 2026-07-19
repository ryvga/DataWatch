import sqlite3
import sys
from types import SimpleNamespace

import pytest

from app.connectors.duckdb import DuckDBConnector
from app.connectors.mysql import MySQLConnector
from app.connectors.sqlite import SQLiteConnector
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
