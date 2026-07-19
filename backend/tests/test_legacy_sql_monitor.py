from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.connectors.duckdb import DuckDBConnector
from app.connectors.postgres import PostgresConnector
from app.connectors.sqlite import SQLiteConnector
from app.services.legacy_sql_monitor import (
    LegacySqlPolicyError,
    LegacySqlResultError,
    execute_legacy_monitor,
    validate_legacy_sql,
    violation_count_from_result,
)


def _validate(sql: str) -> str:
    return validate_legacy_sql(
        sql,
        "P2",
        source_type="postgres",
        target_schema="public",
        target_table="events",
    )


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) AS violations FROM public.events",
        (
            "SELECT COUNT(*) AS violations FROM public.events "
            "WHERE status = 'DELETE is data, not syntax'"
        ),
        (
            "WITH scoped AS (SELECT id FROM public.events) "
            "SELECT COUNT(*) AS violations FROM scoped"
        ),
    ],
)
def test_legacy_sql_policy_accepts_scoped_single_select(sql):
    assert _validate(sql) == sql


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("SELECT 0 AS violations", "must read from the monitored table"),
        ("SELECT COUNT(*) FROM events", "must include the monitored schema"),
        ("SELECT COUNT(*) FROM private.events", "monitored schema"),
        ("SELECT COUNT(*) FROM public.users", "monitored table"),
        (
            "SELECT COUNT(*) FROM public.events JOIN public.users USING (id)",
            "monitored table",
        ),
        ("SELECT COUNT(*) FROM analytics.public.events", "Cross-catalog"),
        (
            "SELECT pg_sleep(3), COUNT(*) FROM public.events",
            "prohibited function: pg_sleep",
        ),
        (
            "SELECT COUNT(*) FROM read_csv_auto('/etc/passwd'), public.events",
            "prohibited function: read_csv_auto",
        ),
        (
            "SELECT COUNT(*) INTO event_backup FROM public.events",
            "prohibited write or lock",
        ),
        (
            "SELECT COUNT(*) FROM public.events FOR UPDATE",
            "prohibited write or lock",
        ),
        (
            "SELECT COUNT(*) FROM public.events; DELETE FROM public.events",
            "exactly one SELECT",
        ),
        ("DELETE FROM public.events", "exactly one SELECT"),
    ],
)
def test_legacy_sql_policy_rejects_attack_corpus(sql, message):
    with pytest.raises(LegacySqlPolicyError, match=message):
        _validate(sql)


@pytest.mark.parametrize("value", [0, 4, Decimal("12")])
def test_violation_count_accepts_non_negative_integer_scalars(value):
    assert violation_count_from_result({"violations": value}) == int(value)


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"a": 1, "b": 2},
        {"violations": True},
        {"violations": "0"},
        {"violations": -1},
        {"violations": 1.5},
        {"violations": float("nan")},
        {"violations": float("inf")},
        {"violations": 2**63},
    ],
)
def test_violation_count_rejects_fail_open_results(result):
    with pytest.raises(LegacySqlResultError):
        violation_count_from_result(result)


@pytest.mark.asyncio
async def test_execute_legacy_monitor_uses_restricted_path_and_timeout():
    calls = []

    class Connector:
        async def execute_monitor_query(self, query, *, timeout_seconds):
            calls.append((query, timeout_seconds))
            return {"violations": 2}

    result, count = await execute_legacy_monitor(
        Connector(), "SELECT COUNT(*) FROM public.events", timeout_seconds=5
    )

    assert result == {"violations": 2}
    assert count == 2
    assert calls == [("SELECT COUNT(*) FROM public.events", 5)]


@pytest.mark.asyncio
async def test_execute_legacy_monitor_fails_closed_on_timeout():
    class Connector:
        async def execute_monitor_query(self, query, *, timeout_seconds):
            raise TimeoutError

    with pytest.raises(LegacySqlResultError, match="timeout"):
        await execute_legacy_monitor(
            Connector(), "SELECT COUNT(*) FROM public.events", timeout_seconds=1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_type", [DuckDBConnector, SQLiteConnector])
async def test_local_connector_monitor_paths_enforce_exact_one_row(connector_type):
    connector = connector_type({"path": ":memory:"})
    try:
        with pytest.raises(ValueError, match="exactly one row"):
            await connector.execute_monitor_query(
                "SELECT 1 AS violations UNION ALL SELECT 2", timeout_seconds=2
            )
    finally:
        await connector.close()


def test_postgres_connection_parameters_do_not_build_a_dsn_string():
    connector = PostgresConnector(
        {
            "host": "db.internal options='-c search_path=attacker'",
            "port": "5432",
            "database": "analytics sslmode=disable",
            "username": "monitor user",
            "password": "space and = signs",
        }
    )

    assert connector._connect_kwargs() == {
        "host": "db.internal options='-c search_path=attacker'",
        "port": 5432,
        "dbname": "analytics sslmode=disable",
        "user": "monitor user",
        "password": "space and = signs",
    }


@pytest.mark.asyncio
async def test_postgres_monitor_path_sets_read_only_timeout_and_rolls_back():
    calls = []

    class Cursor:
        async def fetchmany(self, size):
            assert size == 2
            return [{"violations": 3}]

    class Connection:
        closed = False

        async def execute(self, query, params=None):
            calls.append((query, params))
            return Cursor()

        async def rollback(self):
            calls.append(("ROLLBACK", None))

    connector = PostgresConnector(
        {"host": "db", "database": "analytics", "password": "secret"}
    )
    connector._conn = Connection()

    result = await connector.execute_monitor_query(
        "SELECT COUNT(*) AS violations FROM public.events",
        timeout_seconds=7,
    )

    assert result == {"violations": 3}
    assert calls == [
        ("SET TRANSACTION READ ONLY", None),
        (
            "SELECT set_config('statement_timeout', %s, true)",
            ("7000",),
        ),
        ("SELECT COUNT(*) AS violations FROM public.events", None),
        ("ROLLBACK", None),
    ]


@pytest.mark.asyncio
async def test_ad_hoc_custom_check_does_not_turn_empty_result_into_pass(monkeypatch):
    from app.routers import tables

    table = SimpleNamespace(
        id="table-1",
        source_id="source-1",
        schema_name="main",
        table_name="events",
    )
    source = SimpleNamespace(
        id="source-1",
        type="duckdb",
        connection_config={"encrypted": "encrypted"},
    )

    class Database:
        async def scalar(self, statement):
            return source

    class Connector:
        async def execute_monitor_query(self, query, *, timeout_seconds):
            return {}

        async def close(self):
            return None

    async def get_table(table_id, org, db):
        return table

    monkeypatch.setattr(tables, "_get_table_or_404", get_table)
    monkeypatch.setattr(tables, "decrypt_config", lambda encrypted, org_id: {})
    monkeypatch.setattr(
        tables.ConnectorFactory,
        "create",
        lambda source_type, config: Connector(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await tables.run_custom_check(
            "table-1",
            tables.CustomCheckRequest(
                name="Empty result",
                sql="SELECT COUNT(*) AS violations FROM main.events",
            ),
            org=SimpleNamespace(id="org-1"),
            db=Database(),
        )

    assert exc_info.value.status_code == 422
    assert "exactly one row" in exc_info.value.detail
