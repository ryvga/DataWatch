import os
import socket
import uuid
from dataclasses import replace

import pytest

from app.connectors.cassandra import CassandraConnector
from app.services.cassandra_monitor import (
    CASSANDRA_PLANNER_VERSION,
    compile_cassandra_plan,
)
from app.services.monitor_compiler import MonitorPlanError
from app.services.monitor_dsl import MonitorDefinition
from app.services.monitor_runtime import MonitorExecutionError, execute_partition_plan
from app.services.schema_binding import build_relation_binding


DDL = """CREATE TABLE "analytics"."events" (
  "tenant_id" text is_partition_key=true is_clustering_key=false,
  "event_id" int is_partition_key=false is_clustering_key=true,
  "amount" double is_partition_key=false is_clustering_key=false,
  "status" text is_partition_key=false is_clustering_key=false
);"""


def _relation(asset_id):
    return build_relation_binding(
        asset_id=asset_id,
        source_type="cassandra",
        schema_name="analytics",
        table_name="events",
        ddl=DDL,
        latest_schema_fingerprint=None,
    )


def _definition(asset_id, *, bindings=None, max_rows=10, measurement=None):
    measurement = measurement or {
        "id": "rows",
        "type": "metric",
        "metric": "row_count",
    }
    reference = (
        measurement["id"] if measurement["type"] == "metric" else f"{measurement['id']}.{measurement['output'][0]}"
    )
    return MonitorDefinition.model_validate(
        {
            "apiVersion": "datawatch.io/v1alpha1",
            "kind": "Monitor",
            "metadata": {"name": "cassandra-partition-monitor"},
            "spec": {
                "target": {"assetId": str(asset_id)},
                "trigger": {"type": "manual"},
                "measurements": [measurement],
                "breachWhen": {
                    "op": "lte",
                    "left": {"ref": reference},
                    "right": {"literal": 0},
                },
                "execution": {
                    "timeoutSeconds": 10,
                    "maxRowsScanned": max_rows,
                    "partitionBindings": bindings if bindings is not None else {"tenant_id": "tenant-a"},
                    "sampling": {"mode": "off"},
                },
            },
        }
    )


class _Bound:
    def __init__(self, values):
        self.values = values
        self.fetch_size = None


class _Prepared:
    def __init__(self):
        self.bound = None

    def bind(self, values):
        self.bound = _Bound(values)
        return self.bound


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.prepared = None
        self.timeout = None

    def prepare(self, statement):
        self.statement = statement
        self.prepared = _Prepared()
        return self.prepared

    def execute(self, bound, timeout):
        assert bound is self.prepared.bound
        self.timeout = timeout
        return self.rows


def test_cassandra_plan_requires_exact_partition_bindings_and_row_bound():
    asset_id = uuid.uuid4()
    relation = _relation(asset_id)
    plan = compile_cassandra_plan(_definition(asset_id), relation=relation, ddl=DDL)
    payload = plan.payload()

    assert payload["plannerVersion"] == CASSANDRA_PLANNER_VERSION
    assert payload["relation"]["partitionKeys"] == ["tenant_id"]
    assert plan.statement == ('SELECT "tenant_id" FROM "analytics"."events" WHERE "tenant_id" = ? LIMIT 11')
    assert "tenant-a" not in plan.statement
    assert payload["execution"] == {
        "timeoutSeconds": 10,
        "maxRowsScanned": 10,
        "prepared": True,
    }

    with pytest.raises(MonitorPlanError) as missing:
        compile_cassandra_plan(
            _definition(asset_id, bindings={}),
            relation=relation,
            ddl=DDL,
        )
    assert missing.value.code == "partition_bindings_incomplete"

    with pytest.raises(MonitorPlanError) as unbounded:
        compile_cassandra_plan(
            _definition(asset_id, max_rows=None),
            relation=relation,
            ddl=DDL,
        )
    assert unbounded.value.code == "max_rows_scanned_required"


@pytest.mark.asyncio
async def test_cassandra_runtime_prepares_binds_and_evaluates_without_raw_cql():
    asset_id = uuid.uuid4()
    plan = compile_cassandra_plan(
        _definition(
            asset_id,
            measurement={
                "id": "bad_rows",
                "type": "violations",
                "violationWhen": {
                    "op": "eq",
                    "left": {"field": "status"},
                    "right": {"literal": "failed"},
                },
                "output": ["count", "rate"],
            },
        ),
        relation=_relation(asset_id),
        ddl=DDL,
    )
    session = _Session(
        [
            {"status": "failed"},
            {"status": "ok"},
        ]
    )
    connector = CassandraConnector({"hosts": "unused", "keyspace": "analytics", "tls_mode": "disabled"})
    connector._session = session

    measurements = await execute_partition_plan(connector, plan)

    assert measurements == {"bad_rows.count": 1, "bad_rows.rate": 0.5}
    assert session.statement == plan.statement
    assert session.prepared.bound.values == ("tenant-a",)
    assert session.prepared.bound.fetch_size == 11
    assert session.timeout == 10

    with pytest.raises(NotImplementedError, match="typed partition plan"):
        await connector.execute_profile_query("TRUNCATE analytics.events")


@pytest.mark.asyncio
async def test_cassandra_runtime_rejects_statement_mutation_and_row_overflow():
    asset_id = uuid.uuid4()
    plan = compile_cassandra_plan(_definition(asset_id), relation=_relation(asset_id), ddl=DDL)
    connector = CassandraConnector({"hosts": "unused", "keyspace": "analytics", "tls_mode": "disabled"})
    connector._session = _Session([])

    with pytest.raises(MonitorExecutionError) as mutated:
        await execute_partition_plan(
            connector,
            replace(plan, statement="DELETE FROM analytics.events"),
        )
    assert mutated.value.code == "execution_failed"

    connector._session = _Session([{"tenant_id": "tenant-a"}] * 11)
    with pytest.raises(MonitorExecutionError) as overflow:
        await execute_partition_plan(connector, plan)
    assert overflow.value.code == "row_scan_budget_exceeded"


def test_cassandra_plan_rejects_fixed_schema_missing_predicate():
    asset_id = uuid.uuid4()
    definition = _definition(
        asset_id,
        measurement={
            "id": "missing",
            "type": "violations",
            "violationWhen": {
                "op": "is_missing",
                "value": {"field": "status"},
            },
            "output": ["count"],
        },
    )
    with pytest.raises(MonitorPlanError) as unsupported:
        compile_cassandra_plan(definition, relation=_relation(asset_id), ddl=DDL)
    assert unsupported.value.code == "predicate_not_supported"


@pytest.mark.asyncio
async def test_cassandra_real_partition_plan_connection_schema_execution_and_cleanup():
    try:
        probe = socket.create_connection(("127.0.0.1", 9043), timeout=0.2)
        probe.close()
    except OSError:
        if os.environ.get("REQUIRE_TEST_SERVICES", "").lower() in {"1", "true", "yes"}:
            pytest.fail("Cassandra test service unavailable while REQUIRE_TEST_SERVICES=1")
        pytest.skip("Cassandra test service unavailable")

    from cassandra.cluster import Cluster

    cluster = Cluster(["127.0.0.1"], port=9043)
    session = cluster.connect()
    session.execute(
        "CREATE KEYSPACE IF NOT EXISTS datawatch_partition_test "
        "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}"
    )
    session.execute(
        "CREATE TABLE IF NOT EXISTS datawatch_partition_test.events ("
        "tenant_id text, event_id int, amount double, status text, "
        "PRIMARY KEY ((tenant_id), event_id))"
    )
    session.execute("TRUNCATE datawatch_partition_test.events")
    insert = session.prepare(
        "INSERT INTO datawatch_partition_test.events (tenant_id, event_id, amount, status) VALUES (?, ?, ?, ?)"
    )
    for row in [
        ("tenant-a", 1, 10.0, "ok"),
        ("tenant-a", 2, 20.0, "failed"),
        ("tenant-a", 3, 30.0, "ok"),
        ("tenant-b", 1, 99.0, "other"),
    ]:
        session.execute(insert, row)

    connector = CassandraConnector(
        {
            "hosts": "127.0.0.1",
            "port": 9043,
            "keyspace": "datawatch_partition_test",
            "tls_mode": "disabled",
        }
    )
    try:
        assert await connector.test_connection()
        schemas = await connector.discover_schemas()
        assert [schema.name for schema in schemas] == ["datawatch_partition_test"]
        ddl = await connector.get_table_ddl("datawatch_partition_test", "events")
        assert '"tenant_id" text is_partition_key=true' in ddl
        asset_id = uuid.uuid4()
        relation = build_relation_binding(
            asset_id=asset_id,
            source_type="cassandra",
            schema_name="datawatch_partition_test",
            table_name="events",
            ddl=ddl,
            latest_schema_fingerprint=None,
        )
        plan = compile_cassandra_plan(
            _definition(asset_id, max_rows=10),
            relation=relation,
            ddl=ddl,
        )
        assert await execute_partition_plan(connector, plan) == {"rows": 3}

        capped = compile_cassandra_plan(
            _definition(asset_id, max_rows=2),
            relation=relation,
            ddl=ddl,
        )
        with pytest.raises(MonitorExecutionError) as overflow:
            await execute_partition_plan(connector, capped)
        assert overflow.value.code == "row_scan_budget_exceeded"
    finally:
        await connector.close()
        session.execute("DROP KEYSPACE IF EXISTS datawatch_partition_test")
        cluster.shutdown()
