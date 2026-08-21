import os
import sys
from types import SimpleNamespace

import pytest

from app.connectors.redis import RedisConnector
from app.services.profiler import ProfilerService


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
        return [self.client.values[operation, key] for operation, key in self.operations]


class _Redis:
    def __init__(self, pages, values):
        self.pages = list(pages)
        self.values = values
        self.operations = []
        self.closed = False

    async def ping(self):
        return True

    async def dbsize(self):
        return 99

    async def scan(self, *, cursor, match, count):
        self.operations.append(("scan", cursor, match, count))
        return self.pages.pop(0)

    def pipeline(self, *, transaction):
        assert transaction is False
        return _Pipeline(self)

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_redis_profile_uses_bounded_scan_and_never_reads_values():
    keys = [b"app:string", b"app:hash", b"app:stream"]
    values = {
        ("type", keys[0]): b"string",
        ("pttl", keys[0]): 5_000,
        ("memory_usage", keys[0]): 64,
        ("type", keys[1]): b"hash",
        ("pttl", keys[1]): -1,
        ("memory_usage", keys[1]): 128,
        ("type", keys[2]): b"stream",
        ("pttl", keys[2]): -1,
        ("memory_usage", keys[2]): 256,
        ("hlen", keys[1]): 3,
        ("xlen", keys[2]): 8,
        ("xinfo_groups", keys[2]): [{b"pending": 2, b"lag": 4}],
    }
    client = _Redis([(7, keys[:2]), (0, [keys[0], keys[2]])], values)
    connector = RedisConnector(
        {
            "host": "redis.example.com",
            "database": 4,
            "tls_mode": "disabled",
            "key_pattern": "app:*",
            "max_scan_keys": 100,
            "scan_count": 10,
        }
    )
    connector._client = client

    schemas = await connector.discover_schemas()
    assert schemas[0].name == "db4"
    assert schemas[0].tables[0].name == "keyspace"
    assert schemas[0].tables[0].estimated_rows is None
    snapshot, fields = await connector.get_table_schema("db4", "keyspace")
    assert snapshot.startswith('CREATE KEYSPACE VIEW "db4"."keyspace"')
    assert "stream_pending" in fields

    result = await ProfilerService().profile(connector, "db4", "keyspace")

    assert result.error is None
    assert result.row_count == 3
    metrics = result.column_metrics["_keyspace"]
    assert metrics["scan_complete"] is True
    assert metrics["type_distribution"] == {
        "hash": 1,
        "stream": 1,
        "string": 1,
    }
    assert metrics["ttl_expiring_keys"] == 1
    assert metrics["persistent_keys"] == 2
    assert metrics["memory_bytes"] == 448
    assert metrics["hash_fields"] == 3
    assert metrics["stream_entries"] == 8
    assert metrics["stream_groups"] == 1
    assert metrics["stream_pending"] == 2
    assert metrics["stream_lag"] == 4
    assert metrics["unavailable_metrics"] == []
    assert result.profile_provenance["count_mode"] == "exact"
    assert result.profile_provenance["values_collected"] is False
    assert "key_pattern" not in result.profile_provenance
    assert len(result.profile_provenance["key_pattern_sha256"]) == 64
    assert not any(operation[0] in {"get", "keys", "hgetall", "xrange"} for operation in client.operations)

    with pytest.raises(NotImplementedError):
        await connector.execute_profile_query("FLUSHALL")
    with pytest.raises(NotImplementedError):
        await connector.execute_monitor_query("GET secret")
    await connector.close()
    assert client.closed is True


@pytest.mark.asyncio
async def test_redis_scan_limit_records_lower_bound_provenance():
    keys = [f"app:{index}".encode() for index in range(30)]
    values = {}
    for key in keys[:25]:
        values[("type", key)] = b"string"
        values[("pttl", key)] = -1
        values[("memory_usage", key)] = 10
    # Even a cursor-0 final page is incomplete when the hard ceiling truncates it.
    client = _Redis([(0, keys)], values)
    connector = RedisConnector(
        {
            "host": "redis.example.com",
            "database": 0,
            "tls_mode": "disabled",
            "max_scan_keys": 25,
            "scan_count": 10,
        }
    )
    connector._client = client

    payload = await connector.collect_native_profile("db0", "keyspace", None)

    assert payload["row_count"] == 25
    assert payload["profile_provenance"]["scan_complete"] is False
    assert payload["profile_provenance"]["count_mode"] == "lower_bound"


@pytest.mark.asyncio
async def test_redis_acl_metric_failures_are_explicit_not_silent_zeroes():
    key = b"app:string"
    client = _Redis(
        [(0, [key])],
        {
            ("type", key): b"string",
            ("pttl", key): RuntimeError("NOPERM"),
            ("memory_usage", key): RuntimeError("NOPERM"),
        },
    )
    connector = RedisConnector(
        {
            "host": "redis.example.com",
            "tls_mode": "disabled",
            "max_scan_keys": 25,
            "scan_count": 10,
        }
    )
    connector._client = client

    payload = await connector.collect_native_profile("db0", "keyspace", None)

    metrics = payload["column_metrics"]["_keyspace"]
    assert metrics["memory_bytes"] is None
    assert metrics["unavailable_metrics"] == ["memory", "ttl"]


def test_redis_client_enforces_tls_timeouts_pool_and_no_value_decoding(monkeypatch):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "redis.asyncio", SimpleNamespace(Redis=Client))
    connector = RedisConnector(
        {
            "host": "redis.example.com",
            "database": 2,
            "username": "monitor",
            "password": "secret",
        }
    )

    connector._get_client()

    assert captured["ssl"] is True
    assert captured["ssl_cert_reqs"] == "required"
    assert captured["ssl_check_hostname"] is True
    assert captured["socket_connect_timeout"] == 10
    assert captured["socket_timeout"] == 30
    assert captured["max_connections"] == 5
    assert captured["decode_responses"] is False


@pytest.mark.asyncio
async def test_redis_container_connection_discovery_schema_and_native_profile():
    import redis.asyncio as redis_async

    client = redis_async.Redis(host="127.0.0.1", port=6379, db=14)
    try:
        await client.ping()
    except Exception:
        await client.aclose()
        if os.environ.get("REQUIRE_TEST_SERVICES", "").lower() in {"1", "true", "yes"}:
            pytest.fail("Redis test service unavailable while REQUIRE_TEST_SERVICES=1")
        pytest.skip("Redis test service unavailable")

    prefix = "datawatch-connector-test"
    cursor = 0
    try:
        while True:
            cursor, existing = await client.scan(cursor, match=f"{prefix}:*")
            if existing:
                await client.delete(*existing)
            if cursor == 0:
                break
        await client.set(f"{prefix}:string", "not-collected", px=60_000)
        await client.hset(f"{prefix}:hash", mapping={"secret": "not-collected"})
        stream = f"{prefix}:stream"
        await client.xadd(stream, {"payload": "not-collected"})
        await client.xgroup_create(stream, "monitor-group", id="0", mkstream=True)

        connector = RedisConnector(
            {
                "host": "127.0.0.1",
                "port": 6379,
                "database": 14,
                "tls_mode": "disabled",
                "key_pattern": f"{prefix}:*",
                "max_scan_keys": 100,
                "scan_count": 10,
            }
        )
        try:
            assert await connector.test_connection()
            schemas = await connector.discover_schemas()
            assert schemas[0].name == "db14"
            result = await ProfilerService().profile(connector, "db14", "keyspace")
            assert result.error is None
            assert result.row_count == 3
            metrics = result.column_metrics["_keyspace"]
            assert metrics["type_distribution"] == {
                "hash": 1,
                "stream": 1,
                "string": 1,
            }
            assert metrics["hash_fields"] == 1
            assert metrics["stream_entries"] == 1
            assert metrics["stream_groups"] == 1
            assert metrics["scan_complete"] is True
        finally:
            await connector.close()
    finally:
        cursor = 0
        while True:
            cursor, existing = await client.scan(cursor, match=f"{prefix}:*")
            if existing:
                await client.delete(*existing)
            if cursor == 0:
                break
        await client.aclose()
