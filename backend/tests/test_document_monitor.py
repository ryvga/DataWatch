import json
import os
import socket
import uuid
from dataclasses import replace

import pytest

from app.connectors.base import ConnectorConfigurationError
from app.connectors.mongodb import MongoDBConnector
from app.services.document_monitor import (
    DOCUMENT_PLANNER_VERSION,
    compile_document_plan,
)
from app.services.monitor_compiler import MonitorPlanError
from app.services.monitor_dsl import MonitorDefinition
from app.services.monitor_runtime import MonitorExecutionError, execute_document_plan
from app.services.schema_binding import build_relation_binding


def _definition(
    asset_id,
    *,
    measurement=None,
    max_documents=100,
    max_bytes=None,
) -> MonitorDefinition:
    measurement_body = measurement or {
        "id": "rows",
        "type": "metric",
        "metric": "row_count",
    }
    breach_ref = (
        measurement_body["id"]
        if measurement_body["type"] == "metric"
        else f"{measurement_body['id']}.{measurement_body['output'][0]}"
    )
    execution = {
        "timeoutSeconds": 10,
        "maxDocumentsScanned": max_documents,
        "sampling": {"mode": "off"},
    }
    if max_bytes is not None:
        execution["maxBytesScanned"] = max_bytes
    return MonitorDefinition.model_validate(
        {
            "apiVersion": "datawatch.io/v1alpha1",
            "kind": "Monitor",
            "metadata": {"name": "mongo-bounded-monitor"},
            "spec": {
                "target": {"assetId": str(asset_id)},
                "measurements": [measurement_body],
                "breachWhen": {
                    "op": "lte",
                    "left": {"ref": breach_ref},
                    "right": {"literal": 0},
                },
                "execution": execution,
            },
        }
    )


def _relation(asset_id):
    return build_relation_binding(
        asset_id=asset_id,
        source_type="mongodb",
        schema_name="analytics",
        table_name="events",
        ddl=('CREATE COLLECTION "analytics"."events" ("amount" number NULL, "status" string NULL);'),
        latest_schema_fingerprint=None,
    )


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    async def to_list(self, length):
        return self.rows[:length]

    async def close(self):
        self.closed = True


class _Collection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.cursor = None

    async def aggregate(self, pipeline, **kwargs):
        self.calls.append((pipeline, kwargs))
        self.cursor = _Cursor(self.rows)
        return self.cursor


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "events"
        return self.collection


class _Client:
    def __init__(self, database):
        self.database = database

    def __getitem__(self, name):
        assert name == "analytics"
        return self.database


def _connector(rows):
    collection = _Collection(rows)
    connector = MongoDBConnector(
        {
            "uri": "mongodb://unused",
            "database": "analytics",
            "tls_mode": "disabled",
        }
    )
    connector._client = _Client(_Database(collection))
    return connector, collection


def test_document_plan_is_canonical_bounded_and_immutable():
    asset_id = uuid.uuid4()
    plan = compile_document_plan(_definition(asset_id), relation=_relation(asset_id))
    payload = plan.payload()

    assert payload["plannerVersion"] == DOCUMENT_PLANNER_VERSION
    assert payload["kind"] == "mongodb_bounded_aggregate"
    assert payload["pipeline"][0] == {"$limit": 101}
    assert payload["pipeline"][1]["$group"]["dw_documents_scanned"] == {"$sum": 1}
    assert payload["execution"] == {
        "timeoutSeconds": 10,
        "maxDocumentsScanned": 100,
        "allowDiskUse": False,
        "batchSize": 1,
    }
    assert len(payload["planHash"]) == 64

    first = plan.pipeline()
    first[0]["$limit"] = 999
    assert plan.pipeline()[0] == {"$limit": 101}


def test_document_plan_requires_supported_explicit_cost_boundary():
    asset_id = uuid.uuid4()
    relation = _relation(asset_id)
    with pytest.raises(MonitorPlanError) as missing:
        compile_document_plan(
            _definition(asset_id, max_documents=None),
            relation=relation,
        )
    assert missing.value.code == "max_documents_scanned_required"

    with pytest.raises(MonitorPlanError) as bytes_only:
        compile_document_plan(
            _definition(asset_id, max_bytes=10_000),
            relation=relation,
        )
    assert bytes_only.value.code == "max_bytes_scanned_not_supported"


@pytest.mark.asyncio
async def test_document_runtime_executes_allowlisted_pipeline_without_literal_injection():
    asset_id = uuid.uuid4()
    definition = _definition(
        asset_id,
        measurement={
            "id": "bad_status",
            "type": "violations",
            "violationWhen": {
                "op": "eq",
                "left": {"field": "status"},
                "right": {"literal": "$$ROOT"},
            },
            "output": ["count", "rate"],
        },
    )
    plan = compile_document_plan(definition, relation=_relation(asset_id))
    serialized = json.dumps(plan.pipeline())
    assert '"$literal": "$$ROOT"' in serialized

    connector, collection = _connector(
        [
            {
                "dw_documents_scanned": 4,
                "dw_m0_count": 1,
                "dw_m0_rate": 0.25,
            }
        ]
    )
    measurements = await execute_document_plan(connector, plan)

    assert measurements == {"bad_status.count": 1, "bad_status.rate": 0.25}
    pipeline, options = collection.calls[0]
    assert pipeline == plan.pipeline()
    assert options == {"maxTimeMS": 10_000, "allowDiskUse": False, "batchSize": 1}
    assert collection.cursor.closed is True


@pytest.mark.asyncio
async def test_document_runtime_rejects_stage_mutation_and_scan_overflow():
    asset_id = uuid.uuid4()
    plan = compile_document_plan(_definition(asset_id), relation=_relation(asset_id))
    connector, _ = _connector([{"dw_documents_scanned": 0, "dw_m0": 0}])
    mutated = replace(plan, pipeline_json='[{"$out":"exfiltrated"}]')

    with pytest.raises(ConnectorConfigurationError, match="allowlist"):
        await connector.execute_document_monitor(mutated)

    connector, collection = _connector([{"dw_documents_scanned": 101, "dw_m0": 101}])
    with pytest.raises(MonitorExecutionError) as exceeded:
        await execute_document_plan(connector, plan)
    assert exceeded.value.code == "document_scan_budget_exceeded"
    assert collection.cursor.closed is True


def test_document_schema_fingerprint_matches_native_sample_contract():
    relation = _relation(uuid.uuid4())
    assert len(relation.schema_fingerprint) == 64
    same = build_relation_binding(
        asset_id=relation.asset_id,
        source_type="mongodb",
        schema_name="analytics",
        table_name="events",
        ddl=('CREATE COLLECTION "analytics"."events" ("amount" number NULL, "status" string NULL);'),
        latest_schema_fingerprint=relation.schema_fingerprint,
    )
    assert same.schema_fingerprint == relation.schema_fingerprint


@pytest.mark.asyncio
async def test_document_plan_real_mongodb_bounded_execution_and_cleanup():
    try:
        probe = socket.create_connection(("127.0.0.1", 27018), timeout=0.2)
        probe.close()
    except OSError:
        if os.environ.get("REQUIRE_TEST_SERVICES", "").lower() in {"1", "true", "yes"}:
            pytest.fail("MongoDB test service unavailable while REQUIRE_TEST_SERVICES=1")
        pytest.skip("MongoDB test service unavailable")

    from pymongo import AsyncMongoClient

    collection_name = f"document_monitor_{uuid.uuid4().hex}"
    uri = "mongodb://datawatch-root:datawatch-root@127.0.0.1:27018/?authSource=admin"
    client = AsyncMongoClient(uri)
    collection = client["datawatch_nosql"][collection_name]
    await collection.insert_many(
        [
            {"amount": 10, "status": "paid"},
            {"amount": 20, "status": "paid"},
            {"amount": 30, "status": "pending"},
        ]
    )
    connector = MongoDBConnector(
        {
            "uri": uri,
            "database": "datawatch_nosql",
            "tls_mode": "disabled",
        }
    )
    asset_id = uuid.uuid4()
    relation = build_relation_binding(
        asset_id=asset_id,
        source_type="mongodb",
        schema_name="datawatch_nosql",
        table_name=collection_name,
        ddl=(
            f'CREATE COLLECTION "datawatch_nosql"."{collection_name}" ('
            '"amount" number NOT NULL, "status" string NOT NULL);'
        ),
        latest_schema_fingerprint=None,
    )
    try:
        plan = compile_document_plan(
            _definition(asset_id, max_documents=10),
            relation=relation,
        )
        assert await execute_document_plan(connector, plan) == {"rows": 3}

        capped = compile_document_plan(
            _definition(asset_id, max_documents=2),
            relation=relation,
        )
        with pytest.raises(MonitorExecutionError) as exceeded:
            await execute_document_plan(connector, capped)
        assert exceeded.value.code == "document_scan_budget_exceeded"
    finally:
        await connector.close()
        await collection.drop()
        await client.close()
