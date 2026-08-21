import sqlite3
from dataclasses import replace
from decimal import Decimal

import pytest

from app.connectors.base import ScanBudgetExceeded, ScanBudgetUnsupported
from app.connectors.duckdb import DuckDBConnector
from app.connectors.postgres import PostgresConnector
from app.connectors.sqlite import SQLiteConnector
from app.services.monitor_compiler import compile_relational_plan
from app.services.monitor_dsl import MonitorDefinition
from app.services.monitor_evaluator import PolicyState
from app.services.monitor_runtime import (
    MonitorExecutionError,
    execute_and_evaluate_compiled_plan,
    execute_compiled_plan,
)
from app.services.schema_binding import build_relation_binding
from tests.test_monitor_dsl import valid_definition


def _plan(source_type: str, schema_name: str, table_name: str):
    definition = MonitorDefinition.model_validate(valid_definition())
    relation = build_relation_binding(
        asset_id=definition.spec.target.asset_id,
        source_type=source_type,
        schema_name=schema_name,
        table_name=table_name,
        ddl=(
            f"CREATE TABLE {schema_name}.{table_name} ("
            "status text NULL, payment_reference text NULL"
            ");"
        ),
        latest_schema_fingerprint=None,
    )
    return compile_relational_plan(definition, relation=relation)


@pytest.mark.asyncio
async def test_duckdb_compiled_monitor_executes_with_driver_bound_values(tmp_path):
    import duckdb

    database_path = tmp_path / "compiled.duckdb"
    setup = duckdb.connect(str(database_path))
    setup.execute("CREATE TABLE main.orders (status VARCHAR, payment_reference VARCHAR)")
    setup.execute(
        "INSERT INTO main.orders VALUES "
        "('paid', NULL), ('paid', 'ref-2'), ('pending', NULL)"
    )
    setup.close()

    connector = DuckDBConnector({"path": str(database_path)})
    try:
        measurements = await execute_compiled_plan(
            connector,
            _plan("duckdb", "main", "orders"),
        )
    finally:
        await connector.close()

    assert measurements == {
        "invalid_orders.count": 1,
        "invalid_orders.rate": pytest.approx(1 / 3),
    }


@pytest.mark.asyncio
async def test_sqlite_compiled_monitor_executes_with_driver_bound_values(tmp_path):
    database_path = tmp_path / "compiled.sqlite"
    setup = sqlite3.connect(database_path)
    setup.execute("CREATE TABLE orders (status TEXT, payment_reference TEXT)")
    setup.executemany(
        "INSERT INTO orders VALUES (?, ?)",
        [("paid", None), ("paid", "ref-2"), ("pending", None)],
    )
    setup.commit()
    setup.close()

    connector = SQLiteConnector({"path": str(database_path)})
    try:
        measurements = await execute_compiled_plan(
            connector,
            _plan("sqlite", "main", "orders"),
        )
    finally:
        await connector.close()

    assert measurements == {
        "invalid_orders.count": 1,
        "invalid_orders.rate": pytest.approx(1 / 3),
    }


@pytest.mark.asyncio
async def test_sqlite_scan_budget_blocks_execution_before_query(tmp_path):
    database_path = tmp_path / "budget.sqlite"
    setup = sqlite3.connect(database_path)
    setup.execute("CREATE TABLE orders (status TEXT, payment_reference TEXT)")
    setup.commit()
    setup.close()

    connector = SQLiteConnector({"path": str(database_path)})
    try:
        with pytest.raises(MonitorExecutionError) as exc:
            await execute_compiled_plan(
                connector,
                replace(
                    _plan("sqlite", "main", "orders"),
                    max_bytes_scanned=1,
                ),
            )
    finally:
        await connector.close()

    assert exc.value.code == "scan_budget_exceeded"


@pytest.mark.asyncio
async def test_sqlite_vertical_slice_executes_and_advances_policy(tmp_path):
    database_path = tmp_path / "policy.sqlite"
    setup = sqlite3.connect(database_path)
    setup.execute("CREATE TABLE orders (status TEXT, payment_reference TEXT)")
    setup.executemany(
        "INSERT INTO orders VALUES (?, ?)",
        [("paid", None), ("paid", "ref-2"), ("pending", None)],
    )
    setup.commit()
    setup.close()

    connector = SQLiteConnector({"path": str(database_path)})
    try:
        result = await execute_and_evaluate_compiled_plan(
            connector,
            _plan("sqlite", "main", "orders"),
            previous_policy_state=PolicyState(
                phase="healthy",
                breach_streak=1,
            ),
        )
    finally:
        await connector.close()

    assert result["measurements"]["invalid_orders.rate"] == pytest.approx(1 / 3)
    assert result["decision"] == {
        "version": "monitor-evaluation/v1",
        "rawState": "breached",
        "runStatus": "failed",
        "effectiveState": "breached",
        "transition": "opened",
        "incidentAction": "open",
        "breachStreak": 2,
        "recoveryStreak": 0,
        "notificationEligible": True,
        "cooldownUntil": result["decision"]["cooldownUntil"],
    }
    assert result["decision"]["cooldownUntil"] is not None


@pytest.mark.asyncio
async def test_hostile_literal_is_bound_and_cannot_change_query_semantics(tmp_path):
    database_path = tmp_path / "hostile.sqlite"
    hostile = "paid' OR 1=1 --"
    setup = sqlite3.connect(database_path)
    setup.execute("CREATE TABLE orders (status TEXT, payment_reference TEXT)")
    setup.executemany(
        "INSERT INTO orders VALUES (?, ?)",
        [(hostile, None), ("paid", None), ("pending", None)],
    )
    setup.commit()
    setup.close()

    body = valid_definition()
    body["spec"]["measurements"][0]["violationWhen"]["all"][0]["right"] = {
        "literal": hostile
    }
    definition = MonitorDefinition.model_validate(body)
    relation = build_relation_binding(
        asset_id=definition.spec.target.asset_id,
        source_type="sqlite",
        schema_name="main",
        table_name="orders",
        ddl="CREATE TABLE orders (status text NULL, payment_reference text NULL);",
        latest_schema_fingerprint=None,
    )
    plan = compile_relational_plan(definition, relation=relation)
    assert hostile not in plan.statement

    connector = SQLiteConnector({"path": str(database_path)})
    try:
        measurements = await execute_compiled_plan(connector, plan)
    finally:
        await connector.close()

    assert measurements["invalid_orders.count"] == 1


@pytest.mark.asyncio
async def test_postgres_compiled_adapter_sets_read_only_timeout_and_bindings():
    calls = []

    class Cursor:
        async def fetchone(self):
            return {"bytes": 8192}

        async def fetchmany(self, size):
            assert size == 2
            return [{"dw_m0_count": 1, "dw_m0_rate": Decimal("0.5")}]

    class Connection:
        closed = False

        async def execute(self, query, params=None):
            calls.append((query, params))
            return Cursor()

        async def rollback(self):
            calls.append(("ROLLBACK", None))

    connector = PostgresConnector({"host": "db", "database": "analytics"})
    connector._conn = Connection()
    plan = _plan("postgres", "analytics", "orders")

    measurements = await execute_compiled_plan(connector, plan)

    assert measurements == {
        "invalid_orders.count": 1,
        "invalid_orders.rate": 0.5,
    }
    assert calls == [
        ("ROLLBACK", None),
        ("SET TRANSACTION READ ONLY", None),
        (
            "SELECT pg_total_relation_size(%s::regclass) AS bytes",
            ('"analytics"."orders"',),
        ),
        ("ROLLBACK", None),
        ("ROLLBACK", None),
        ("SET TRANSACTION READ ONLY", None),
        ("SELECT set_config('statement_timeout', %s, true)", ("30000",)),
        (plan.statement, {"p0": "paid"}),
        ("ROLLBACK", None),
    ]


class FakeConnector:
    profile_dialect = "sqlite"

    def __init__(self, result=None, error=None, budget_error=None):
        self.result = result
        self.error = error
        self.budget_error = budget_error
        self.calls = []

    async def enforce_monitor_scan_budget(self, schema, table, max_bytes_scanned):
        self.calls.append(("budget", schema, table, max_bytes_scanned))
        if self.budget_error:
            raise self.budget_error

    async def execute_compiled_monitor(
        self,
        statement,
        parameters,
        *,
        timeout_seconds,
    ):
        self.calls.append((statement, parameters, timeout_seconds))
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ScanBudgetExceeded(), "scan_budget_exceeded"),
        (ScanBudgetUnsupported(), "scan_budget_not_supported"),
    ],
)
async def test_runtime_fails_closed_when_scan_budget_cannot_be_honored(error, code):
    connector = FakeConnector(
        result={"dw_m0_count": 1, "dw_m0_rate": 0.5},
        budget_error=error,
    )
    with pytest.raises(MonitorExecutionError) as exc:
        await execute_compiled_plan(
            connector,
            _plan("sqlite", "main", "orders"),
        )
    assert exc.value.code == code
    assert connector.calls == [("budget", "main", "orders", 1_000_000_000)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "code"),
    [
        ({"unexpected": 1}, "result_shape_invalid"),
        ({"dw_m0_count": None, "dw_m0_rate": 0.0}, "result_null_invalid"),
        ({"dw_m0_count": True, "dw_m0_rate": 0.0}, "result_type_invalid"),
        ({"dw_m0_count": 1, "dw_m0_rate": "0.5"}, "result_type_invalid"),
        ({"dw_m0_count": 1, "dw_m0_rate": float("nan")}, "result_not_finite"),
        ({"dw_m0_count": 1, "dw_m0_rate": float("inf")}, "result_not_finite"),
    ],
)
async def test_runtime_rejects_fail_open_result_contracts(result, code):
    with pytest.raises(MonitorExecutionError) as exc:
        await execute_compiled_plan(
            FakeConnector(result=result),
            _plan("sqlite", "main", "orders"),
        )
    assert exc.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code"),
    [
        (TimeoutError(), "execution_timeout"),
        (NotImplementedError(), "connector_execution_not_supported"),
        (RuntimeError("credential details"), "execution_failed"),
    ],
)
async def test_runtime_maps_adapter_failures_without_leaking_details(error, code):
    with pytest.raises(MonitorExecutionError) as exc:
        await execute_compiled_plan(
            FakeConnector(error=error),
            _plan("sqlite", "main", "orders"),
        )
    assert exc.value.code == code
    assert "credential details" not in str(exc.value)


@pytest.mark.asyncio
async def test_runtime_rejects_mutated_statement_before_connector_execution():
    connector = FakeConnector(result={"dw_m0_count": 1, "dw_m0_rate": 0.5})
    plan = replace(
        _plan("sqlite", "main", "orders"),
        statement="DELETE FROM orders",
    )

    with pytest.raises(MonitorExecutionError) as exc:
        await execute_compiled_plan(connector, plan)

    assert exc.value.code == "statement_not_read_only"
    assert connector.calls == []


@pytest.mark.asyncio
async def test_runtime_rejects_mutated_parameter_contract_before_execution():
    connector = FakeConnector(result={"dw_m0_count": 1, "dw_m0_rate": 0.5})
    plan = replace(
        _plan("sqlite", "main", "orders"),
        statement=(
            'SELECT 1 AS "dw_m0_count", 0.5 AS "dw_m0_rate" '
            'FROM "main"."orders"'
        ),
    )

    with pytest.raises(MonitorExecutionError) as exc:
        await execute_compiled_plan(connector, plan)

    assert exc.value.code == "parameter_contract_invalid"
    assert connector.calls == []


@pytest.mark.asyncio
async def test_runtime_rejects_mutated_relation_before_execution():
    connector = FakeConnector(result={"dw_m0_count": 1, "dw_m0_rate": 0.5})
    original = _plan("sqlite", "main", "orders")
    plan = replace(
        original,
        statement=original.statement.replace('"main"."orders"', '"main"."users"'),
    )

    with pytest.raises(MonitorExecutionError) as exc:
        await execute_compiled_plan(connector, plan)

    assert exc.value.code == "relation_contract_invalid"
    assert connector.calls == []


@pytest.mark.asyncio
async def test_runtime_rejects_connector_dialect_mismatch_before_execution():
    connector = FakeConnector(result={"dw_m0_count": 1, "dw_m0_rate": 0.5})

    with pytest.raises(MonitorExecutionError) as exc:
        await execute_compiled_plan(
            connector,
            _plan("postgres", "analytics", "orders"),
        )

    assert exc.value.code == "connector_plan_mismatch"
    assert connector.calls == []
