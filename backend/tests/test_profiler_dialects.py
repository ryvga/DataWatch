import sqlite3

import pytest

from app.connectors.base import BaseConnector
from app.services.profiler import ColumnInfo, ProfilerService
from app.tasks import _profile_allows_downstream_checks


def test_sqlite_profile_query_executes_and_returns_core_metrics():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        'CREATE TABLE events ('
        'id INTEGER NOT NULL, amount REAL, name TEXT, created_at TIMESTAMP)'
    )
    conn.executemany(
        "INSERT INTO events VALUES (?, ?, ?, ?)",
        [
            (1, 10.0, "created", "2026-07-19 10:00:00"),
            (2, 0.0, "", "2026-07-19 11:00:00"),
            (3, -5.0, None, "2026-07-19 12:00:00"),
        ],
    )
    columns = [
        ColumnInfo("id", "INTEGER", False),
        ColumnInfo("amount", "REAL"),
        ColumnInfo("name", "TEXT"),
        ColumnInfo("created_at", "TIMESTAMP"),
    ]

    query = ProfilerService().build_profile_query(
        "main",
        "events",
        columns,
        "created_at",
        dialect="sqlite",
    )
    raw = dict(conn.execute(query).fetchone())

    assert raw["_row_count"] == 3
    assert raw["null_rate_name"] == pytest.approx(1 / 3)
    assert raw["distinct_count_name"] == 2
    assert raw["mean_amount"] == pytest.approx(5 / 3)
    assert raw["zero_rate_amount"] == pytest.approx(1 / 3)
    assert raw["negative_rate_amount"] == pytest.approx(1 / 3)
    assert raw["empty_rate_name"] == pytest.approx(1 / 2)
    assert raw["range_seconds_created_at"] == pytest.approx(7200.0, abs=0.01)
    assert raw["_freshness_seconds"] > 0
    assert "::FLOAT" not in query
    assert "PERCENTILE_CONT" not in query


def test_profile_query_quotes_discovered_identifiers():
    query = ProfilerService().build_profile_query(
        'odd"schema',
        'order events',
        [ColumnInfo('select"value', "INTEGER")],
        None,
        dialect="sqlite",
    )

    assert 'FROM "odd""schema"."order events"' in query
    assert '"select""value"' in query


@pytest.mark.asyncio
async def test_top_values_quotes_identifiers_and_bounds_limit():
    captured = []

    class Connector:
        async def execute_query_many(self, query):
            captured.append(query)
            return [{"val": "paid", "cnt": 2}]

    result = await ProfilerService().get_top_values(
        Connector(),
        'odd"schema',
        "order events",
        [ColumnInfo('select"value', "TEXT")],
    )

    assert result == {'select"value': [{"value": "paid", "count": 2}]}
    assert 'FROM "odd""schema"."order events"' in captured[0]
    assert 'CAST("select""value" AS TEXT)' in captured[0]

    with pytest.raises(ValueError, match="between 1 and 100"):
        await ProfilerService().get_top_values(
            Connector(), "main", "events", [ColumnInfo("status", "TEXT")], 101
        )


def test_ddl_parser_preserves_quoted_identifier_spaces_and_quotes():
    assert ProfilerService._split_ddl_column(
        '"order total" double precision NULL'
    ) == ("order total", "double precision NULL")
    assert ProfilerService._split_ddl_column(
        '"say ""hello""" text NOT NULL'
    ) == ('say "hello"', "text NOT NULL")


def test_profile_errors_do_not_allow_anomaly_or_custom_monitor_checks():
    assert _profile_allows_downstream_checks(type("R", (), {"error": None})()) is True
    assert _profile_allows_downstream_checks(type("R", (), {"error": "query failed"})()) is False


class _DiscoveryOnlyConnector(BaseConnector):
    async def test_connection(self):
        return True

    async def discover_schemas(self):
        return []

    async def execute_profile_query(self, query):
        raise AssertionError("unsupported connector must not execute profile SQL")

    async def get_table_ddl(self, schema, table):
        raise AssertionError("unsupported connector must not introspect for profiling")


@pytest.mark.asyncio
async def test_profile_fails_explicitly_for_discovery_only_connector():
    result = await ProfilerService().profile(
        _DiscoveryOnlyConnector(), "public", "events"
    )

    assert result.error == (
        "_DiscoveryOnlyConnector supports connection/discovery but does not yet "
        "support automated profiling"
    )


@pytest.mark.asyncio
async def test_profile_executes_exactly_one_aggregate_query():
    class Connector(BaseConnector):
        profile_dialect = "postgres"

        def __init__(self):
            self.queries = []

        async def test_connection(self):
            return True

        async def discover_schemas(self):
            return []

        async def execute_profile_query(self, query):
            self.queries.append(query)
            return {
                "_row_count": 6_000_000,
                "null_rate_id": 0.0,
                "distinct_count_id": 6_000_000,
                "uniqueness_ratio_id": 1.0,
                "min_id": 1,
                "max_id": 6_000_000,
                "mean_id": 3_000_000.5,
                "stddev_id": 1.0,
                "p25_id": 1_500_000,
                "p50_id": 3_000_000,
                "p75_id": 4_500_000,
                "p95_id": 5_700_000,
                "zero_rate_id": 0.0,
                "negative_rate_id": 0.0,
            }

        async def get_table_ddl(self, schema, table):
            return 'CREATE TABLE "events" (\n"id" integer NOT NULL\n);'

    connector = Connector()
    result = await ProfilerService().profile(connector, "public", "events")

    assert result.error is None
    assert result.row_count == 6_000_000
    assert len(connector.queries) == 1
    assert "TABLESAMPLE" not in connector.queries[0]
    assert "COUNT(*) AS _n" not in connector.queries[0]
