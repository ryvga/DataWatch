import hashlib
import os
import uuid
from dataclasses import replace

import pytest

from app.connectors.redis import RedisConnector
from app.services.monitor_compiler import MonitorPlanError
from app.services.monitor_dsl import MonitorDefinition
from app.services.monitor_runtime import MonitorExecutionError, execute_keyspace_plan
from app.services.redis_monitor import REDIS_PLANNER_VERSION, compile_redis_plan
from app.services.schema_binding import build_relation_binding


PATTERN = "monitor:*"
PATTERN_DIGEST = hashlib.sha256(PATTERN.encode()).hexdigest()
DDL = f"""CREATE KEYSPACE VIEW "db4"."keyspace" (
  "hash_fields" NUMBER NULL,
  "key_type" STRING NOT NULL,
  "memory_bytes" NUMBER NULL,
  "stream_entries" NUMBER NULL,
  "stream_groups" NUMBER NULL,
  "stream_lag" NUMBER NULL,
  "stream_pending" NUMBER NULL,
  "ttl_ms" NUMBER NULL
) WITH key_pattern_sha256='{PATTERN_DIGEST}';"""


def _relation(asset_id, *, ddl=DDL):
    return build_relation_binding(
        asset_id=asset_id,
        source_type="redis",
        schema_name="db4",
        table_name="keyspace",
        ddl=ddl,
        latest_schema_fingerprint=None,
    )


def _definition(asset_id, *, max_keys=10, measurements=None):
    measurements = measurements or [{"id": "keys", "type": "metric", "metric": "row_count"}]
    reference = (
        measurements[0]["id"]
        if measurements[0]["type"] == "metric"
        else f"{measurements[0]['id']}.{measurements[0]['output'][0]}"
    )
    return MonitorDefinition.model_validate(
        {
            "apiVersion": "datawatch.io/v1alpha1",
            "kind": "Monitor",
            "metadata": {"name": "redis-keyspace-monitor"},
            "spec": {
                "target": {"assetId": str(asset_id)},
                "trigger": {"type": "manual"},
                "measurements": measurements,
                "breachWhen": {
                    "op": "lte",
                    "left": {"ref": reference},
                    "right": {"literal": 0},
                },
                "execution": {
                    "timeoutSeconds": 10,
                    "maxKeysScanned": max_keys,
                    "sampling": {"mode": "off"},
                },
            },
        }
    )


class _Pipeline:
    def __init__(self, client):
        self.client = client
        self.operations = []

    def _queue(self, operation, key):
        self.operations.append((operation, key))
        self.client.operations.append((operation, key))
        return self

    def type(self, key):
        return self._queue("type", key)

    def pttl(self, key):
        return self._queue("pttl", key)

    def memory_usage(self, key):
        return self._queue("memory_usage", key)

    def hlen(self, key):
        return self._queue("hlen", key)

    def xlen(self, key):
        return self._queue("xlen", key)

    def xinfo_groups(self, key):
        return self._queue("xinfo_groups", key)

    async def execute(self, raise_on_error=False):
        assert raise_on_error is False
        return [self.client.values[item] for item in self.operations]


class _Redis:
    def __init__(self, pages, values):
        self.pages = list(pages)
        self.values = values
        self.operations = []

    async def scan(self, *, cursor, match, count):
        self.operations.append(("scan", cursor, match, count))
        return self.pages.pop(0)

    def pipeline(self, *, transaction):
        assert transaction is False
        return _Pipeline(self)

    async def aclose(self):
        pass


def _values(keys):
    return {
        ("type", keys[0]): b"string",
        ("pttl", keys[0]): 5_000,
        ("memory_usage", keys[0]): 64,
        ("type", keys[1]): b"hash",
        ("pttl", keys[1]): -1,
        ("memory_usage", keys[1]): 128,
        ("hlen", keys[1]): 3,
        ("type", keys[2]): b"stream",
        ("pttl", keys[2]): -1,
        ("memory_usage", keys[2]): 256,
        ("xlen", keys[2]): 8,
        ("xinfo_groups", keys[2]): [{b"pending": 2, b"lag": 4}],
    }


def test_redis_plan_requires_native_bound_and_binds_scope_fingerprint():
    asset_id = uuid.uuid4()
    plan = compile_redis_plan(_definition(asset_id), relation=_relation(asset_id))
    payload = plan.payload()

    assert payload["plannerVersion"] == REDIS_PLANNER_VERSION
    assert payload["kind"] == "redis_bounded_metadata_scan"
    assert payload["scopeMode"] == "configured_key_pattern"
    assert payload["execution"]["maxKeysScanned"] == 10
    assert payload["resultContract"]["storedValuesRead"] is False

    body = _definition(asset_id).model_dump(mode="json", by_alias=True, exclude_unset=True)
    body["spec"]["execution"].pop("maxKeysScanned")
    with pytest.raises(MonitorPlanError) as missing:
        compile_redis_plan(MonitorDefinition.model_validate(body), relation=_relation(asset_id))
    assert missing.value.code == "max_keys_scanned_required"


@pytest.mark.asyncio
async def test_redis_runtime_uses_only_metadata_commands_and_evaluates_ttl_memory_streams():
    asset_id = uuid.uuid4()
    plan = compile_redis_plan(
        _definition(
            asset_id,
            measurements=[
                {"id": "memory", "type": "metric", "metric": "sum", "field": "memory_bytes"},
                {"id": "persistent", "type": "metric", "metric": "negative_rate", "field": "ttl_ms"},
                {
                    "id": "streams",
                    "type": "violations",
                    "violationWhen": {
                        "op": "eq",
                        "left": {"field": "key_type"},
                        "right": {"literal": "stream"},
                    },
                    "output": ["count"],
                },
            ],
        ),
        relation=_relation(asset_id),
    )
    keys = [b"monitor:string", b"monitor:hash", b"monitor:stream"]
    client = _Redis([(0, keys)], _values(keys))
    connector = RedisConnector(
        {
            "host": "unused",
            "database": 4,
            "tls_mode": "disabled",
            "key_pattern": PATTERN,
            "max_scan_keys": 100,
            "scan_count": 10,
        }
    )
    connector._client = client

    measurements = await execute_keyspace_plan(connector, plan)

    assert measurements == {"memory": 448, "persistent": pytest.approx(2 / 3), "streams.count": 1}
    assert not any(operation[0] in {"get", "keys", "hgetall", "xrange", "eval"} for operation in client.operations)


@pytest.mark.asyncio
async def test_redis_runtime_fails_closed_on_overflow_acl_and_scope_mutation():
    asset_id = uuid.uuid4()
    keys = [b"monitor:1", b"monitor:2", b"monitor:3"]
    values = {}
    for key in keys:
        values[("type", key)] = b"string"
        values[("pttl", key)] = -1
        values[("memory_usage", key)] = 10
    connector = RedisConnector(
        {
            "host": "unused",
            "database": 4,
            "tls_mode": "disabled",
            "key_pattern": PATTERN,
            "max_scan_keys": 100,
            "scan_count": 10,
        }
    )
    overflow_plan = compile_redis_plan(
        _definition(asset_id, max_keys=2),
        relation=_relation(asset_id),
    )
    connector._client = _Redis([(0, keys)], values)
    with pytest.raises(MonitorExecutionError) as overflow:
        await execute_keyspace_plan(connector, overflow_plan)
    assert overflow.value.code == "key_scan_budget_exceeded"

    memory_plan = compile_redis_plan(
        _definition(
            asset_id,
            measurements=[{"id": "memory", "type": "metric", "metric": "sum", "field": "memory_bytes"}],
        ),
        relation=_relation(asset_id),
    )
    acl_values = dict(values)
    acl_values[("memory_usage", keys[0])] = RuntimeError("NOPERM")
    connector._client = _Redis([(0, keys)], acl_values)
    with pytest.raises(MonitorExecutionError) as acl:
        await execute_keyspace_plan(connector, memory_plan)
    assert acl.value.code == "execution_failed"

    connector._client = _Redis([(0, [])], {})
    mutated = replace(memory_plan, relation=replace(memory_plan.relation, schema_fingerprint="0" * 64))
    with pytest.raises(MonitorExecutionError) as scope:
        await execute_keyspace_plan(connector, mutated)
    assert scope.value.code == "execution_failed"

    connector._config["key_pattern"] = "other:*"
    with pytest.raises(MonitorExecutionError) as changed_config:
        await execute_keyspace_plan(connector, memory_plan)
    assert changed_config.value.code == "execution_failed"


@pytest.mark.asyncio
async def test_redis_real_metadata_plan_and_overflow_cleanup():
    import redis.asyncio as redis_async

    client = redis_async.Redis(host="127.0.0.1", port=6379, db=14)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        if os.environ.get("REQUIRE_TEST_SERVICES", "").lower() in {"1", "true", "yes"}:
            pytest.fail("Redis test service unavailable while REQUIRE_TEST_SERVICES=1")
        pytest.skip("Redis test service unavailable")

    prefix = f"datawatch-monitor-{uuid.uuid4().hex}"
    pattern = f"{prefix}:*"
    await client.set(f"{prefix}:string", "not-collected")
    await client.hset(f"{prefix}:hash", mapping={"secret": "not-collected"})
    await client.xadd(f"{prefix}:stream", {"payload": "not-collected"})
    connector = RedisConnector(
        {
            "host": "127.0.0.1",
            "port": 6379,
            "database": 14,
            "tls_mode": "disabled",
            "key_pattern": pattern,
            "max_scan_keys": 100,
            "scan_count": 10,
        }
    )
    try:
        ddl = await connector.get_table_ddl("db14", "keyspace")
        asset_id = uuid.uuid4()
        relation = build_relation_binding(
            asset_id=asset_id,
            source_type="redis",
            schema_name="db14",
            table_name="keyspace",
            ddl=ddl,
            latest_schema_fingerprint=None,
        )
        profile = await connector.collect_native_profile("db14", "keyspace", None)
        assert profile["schema_fingerprint"] == relation.schema_fingerprint
        plan = compile_redis_plan(_definition(asset_id), relation=relation)
        assert await execute_keyspace_plan(connector, plan) == {"keys": 3}

        capped = compile_redis_plan(_definition(asset_id, max_keys=2), relation=relation)
        with pytest.raises(MonitorExecutionError) as overflow:
            await execute_keyspace_plan(connector, capped)
        assert overflow.value.code == "key_scan_budget_exceeded"
    finally:
        await connector.close()
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor, match=pattern)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break
        await client.aclose()
