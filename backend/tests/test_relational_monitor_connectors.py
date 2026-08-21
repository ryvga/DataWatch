import asyncio
from unittest.mock import AsyncMock

import pytest

from app.connectors.base import ScanBudgetExceeded
from app.connectors.mysql import MySQLConnector
from app.connectors.sqlserver import SQLServerConnector
from app.services.monitor_compiler import compile_relational_plan
from app.services.monitor_dsl import MonitorDefinition
from app.services.monitor_runtime import execute_compiled_plan
from app.services.schema_binding import build_relation_binding
from tests.test_monitor_dsl import valid_definition


def _plan(source_type: str, schema: str = "analytics", table: str = "orders"):
    definition = MonitorDefinition.model_validate(valid_definition())
    relation = build_relation_binding(
        asset_id=definition.spec.target.asset_id,
        source_type=source_type,
        schema_name=schema,
        table_name=table,
        ddl=(
            f"CREATE TABLE {schema}.{table} ("
            "status text NULL, payment_reference text NULL);"
        ),
        latest_schema_fingerprint=None,
    )
    return compile_relational_plan(definition, relation=relation)


@pytest.mark.asyncio
async def test_mysql_compiled_monitor_uses_read_only_transaction_and_bindings(monkeypatch):
    import sys
    from types import SimpleNamespace

    dict_cursor = object()
    calls = []

    class Cursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement, parameters=None):
            calls.append((statement, parameters))

        async def fetchmany(self, size):
            assert size == 2
            return [{"dw_m0_count": 1, "dw_m0_rate": 0.5}]

    class Connection:
        def cursor(self, kind=None):
            assert kind is dict_cursor
            return Cursor()

        async def rollback(self):
            calls.append(("ROLLBACK", None))

        def close(self):
            calls.append(("CLOSE", None))

    class Acquire:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_args):
            return None

    class Pool:
        def acquire(self):
            return Acquire()

    monkeypatch.setitem(sys.modules, "aiomysql", SimpleNamespace(DictCursor=dict_cursor))
    connector = MySQLConnector({"host": "db", "database": "analytics"})
    connector._pool = Pool()
    connector.enforce_monitor_scan_budget = AsyncMock()
    plan = _plan("mysql")

    result = await execute_compiled_plan(connector, plan)

    assert result == {"invalid_orders.count": 1, "invalid_orders.rate": 0.5}
    assert calls[0] == ("START TRANSACTION READ ONLY", None)
    assert calls[1][1] == ("paid", "paid")
    assert ":p0" not in calls[1][0]
    assert calls[-1] == ("ROLLBACK", None)


@pytest.mark.asyncio
async def test_mysql_scan_budget_counts_table_and_indexes():
    calls = []

    class Cursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement, parameters=None):
            calls.append((statement, parameters))

        async def fetchone(self):
            return (1_001,)

    class Connection:
        def cursor(self):
            return Cursor()

    class Acquire:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_args):
            return None

    class Pool:
        def acquire(self):
            return Acquire()

    connector = MySQLConnector({"host": "db", "database": "analytics"})
    connector._pool = Pool()

    with pytest.raises(ScanBudgetExceeded):
        await connector.enforce_monitor_scan_budget("analytics", "orders", 1_000)

    assert "data_length" in calls[0][0]
    assert "index_length" in calls[0][0]
    assert calls[0][1] == ("analytics", "orders")


@pytest.mark.asyncio
async def test_mysql_compiled_monitor_timeout_discards_connection(monkeypatch):
    import sys
    from types import SimpleNamespace

    closed = False

    class Cursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement, parameters=None):
            if statement != "START TRANSACTION READ ONLY":
                await asyncio.Event().wait()

    class Connection:
        def cursor(self, _kind=None):
            return Cursor()

        async def rollback(self):
            return None

        def close(self):
            nonlocal closed
            closed = True

    class Acquire:
        async def __aenter__(self):
            return Connection()

        async def __aexit__(self, *_args):
            return None

    class Pool:
        def acquire(self):
            return Acquire()

    monkeypatch.setitem(sys.modules, "aiomysql", SimpleNamespace(DictCursor=object()))
    connector = MySQLConnector({"host": "db", "database": "analytics"})
    connector._pool = Pool()

    with pytest.raises(TimeoutError):
        await connector.execute_compiled_monitor(
            "SELECT COUNT(*) AS dw_m0 FROM analytics.orders",
            {},
            timeout_seconds=0.01,
        )

    assert closed


@pytest.mark.asyncio
async def test_sqlserver_compiled_monitor_rejects_write_capable_principal():
    calls = []

    class Cursor:
        description = [("permission_name",)]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement, parameters=None):
            calls.append((statement, parameters))

        async def fetchone(self):
            return ("UPDATE",)

        def cancel(self):
            return None

    class Connection:
        closed = False

        def cursor(self):
            return Cursor()

    connector = SQLServerConnector({"host": "db", "database": "analytics"})
    connector._conn = Connection()
    connector.enforce_monitor_scan_budget = AsyncMock()

    with pytest.raises(Exception) as exc:
        await execute_compiled_plan(connector, _plan("sqlserver"))

    assert getattr(exc.value, "code", None) == "execution_failed"
    assert "fn_my_permissions" in calls[0][0]
    assert calls[0][1] == ("analytics.orders",)
    assert not any("COUNT(CASE" in statement for statement, _ in calls)


@pytest.mark.asyncio
async def test_sqlserver_compiled_monitor_binds_and_rolls_back():
    calls = []

    class Cursor:
        description = None
        permission_checked = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement, parameters=None):
            calls.append((statement, parameters))
            if "fn_my_permissions" in statement:
                self.permission_checked = True
            elif "COUNT(CASE" in statement:
                self.description = [("dw_m0_count",), ("dw_m0_rate",)]

        async def fetchone(self):
            return None if self.permission_checked else (0,)

        async def fetchmany(self, size):
            assert size == 2
            return [(1, 0.5)]

        def cancel(self):
            return None

    class Connection:
        closed = False

        def cursor(self):
            return Cursor()

    connector = SQLServerConnector({"host": "db", "database": "analytics"})
    connector._conn = Connection()
    connector.enforce_monitor_scan_budget = AsyncMock()

    result = await execute_compiled_plan(connector, _plan("sqlserver"))

    assert result == {"invalid_orders.count": 1, "invalid_orders.rate": 0.5}
    compiled = next(call for call in calls if "COUNT(CASE" in call[0])
    assert compiled[1] == ("paid", "paid")
    assert ":p0" not in compiled[0]
    assert calls[-1][0] == "IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION"


@pytest.mark.asyncio
async def test_sqlserver_scan_budget_counts_in_row_and_lob_allocations():
    calls = []

    class Cursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement, parameters=None):
            calls.append((statement, parameters))

        async def fetchone(self):
            return (1_001,)

    class Connection:
        closed = False

        def cursor(self):
            return Cursor()

    connector = SQLServerConnector({"host": "db", "database": "analytics"})
    connector._conn = Connection()

    with pytest.raises(ScanBudgetExceeded):
        await connector.enforce_monitor_scan_budget("analytics", "orders", 1_000)

    assert "a.type IN (1, 3)" in calls[0][0]
    assert "p.hobt_id" in calls[0][0]
    assert "p.partition_id" in calls[0][0]
    assert calls[0][1] == ("analytics", "orders")


@pytest.mark.asyncio
async def test_sqlserver_compiled_monitor_timeout_cancels_and_discards_connection():
    cancelled = False
    closed = False

    class Cursor:
        description = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement, parameters=None):
            if statement.startswith("SELECT COUNT"):
                await asyncio.Event().wait()

        async def fetchone(self):
            return None

        def cancel(self):
            nonlocal cancelled
            cancelled = True

    class Connection:
        closed = False

        def cursor(self):
            return Cursor()

        async def close(self):
            nonlocal closed
            closed = True

    connector = SQLServerConnector({"host": "db", "database": "analytics"})
    connector._conn = Connection()

    with pytest.raises(TimeoutError):
        await connector.execute_compiled_monitor(
            "SELECT COUNT(*) AS dw_m0 FROM analytics.orders",
            {},
            timeout_seconds=0.01,
        )

    assert cancelled
    assert closed
    assert connector._conn is None
