import json
import socket
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.connectors.base import ConnectorConfigurationError
from app.connectors.cassandra import CassandraConnector
from app.connectors.mongodb import (
    MongoDBConnector,
    _MAX_PROFILE_DOCUMENT_BYTES,
    _summarize_fields,
)
from app.services.profiler import ProfilerService


class _Cursor:
    def __init__(self, documents):
        self.documents = documents
        self._position = 0
        self.closed = False

    def sort(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def max_time_ms(self, *_args):
        return self

    async def to_list(self, length):
        return self.documents[:length]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._position >= len(self.documents):
            raise StopAsyncIteration
        document = self.documents[self._position]
        self._position += 1
        return document

    async def close(self):
        self.closed = True


class _Collection:
    def __init__(self, documents, *, document_count, document_sizes=None):
        self.documents = documents
        self.document_count = document_count
        self.document_sizes = document_sizes or [len(repr(doc).encode()) for doc in documents]
        self.aggregate_calls = []
        self.aggregate_cursors = []
        self.indexes = {"freshness": {"key": [("nested.event_at", -1)]}}
        first_nested = documents[0].get("nested", {}) if documents else {}
        self.freshness_rows = (
            [{"nested": {"event_at": first_nested["event_at"]}}]
            if "event_at" in first_nested
            else []
        )

    async def estimated_document_count(self):
        return self.document_count

    async def aggregate(self, pipeline, **kwargs):
        self.aggregate_calls.append((pipeline, kwargs))
        envelopes = [
            {
                "_datawatch_size": size,
                "_datawatch_document": (
                    document if size <= _MAX_PROFILE_DOCUMENT_BYTES else None
                ),
            }
            for document, size in zip(self.documents, self.document_sizes)
        ]
        cursor = _Cursor(envelopes)
        self.aggregate_cursors.append(cursor)
        return cursor

    async def index_information(self):
        return self.indexes

    def find(self, *_args):
        return _Cursor(self.freshness_rows)


class _Database:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "events"
        return self.collection

    async def list_collection_names(self):
        return ["events"]

    async def command(self, command, collection):
        assert command == "collStats"
        assert collection == "events"
        return {"avgObjSize": 512.0}


class _Client:
    def __init__(self, database):
        self.database = database
        self.admin = SimpleNamespace(command=self._command)
        self.closed = False

    async def _command(self, command):
        assert command == "ping"
        return {"ok": 1}

    def __getitem__(self, name):
        assert name == "analytics"
        return self.database

    async def close(self):
        self.closed = True


def _connector():
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    documents = [
        {
            "_id": 1,
            "amount": 10,
            "status": "paid",
            "nested": {"event_at": now, "special field": "alpha"},
            "sensitive": "customer@example.com",
        },
        {
            "_id": 2,
            "amount": None,
            "status": "",
            "nested": {"event_at": now - timedelta(hours=1)},
            "sensitive": "token-secret-value",
        },
        {
            "_id": 3,
            "amount": -5.0,
            "optional": True,
            "nested": {"event_at": now - timedelta(hours=2)},
        },
    ]
    collection = _Collection(documents, document_count=2**31 + 5)
    connector = MongoDBConnector(
        {
            "uri": "mongodb://unused",
            "database": "analytics",
            "tls_mode": "disabled",
            "profile_sample_size": 100,
        }
    )
    connector._client = _Client(_Database(collection))
    return connector, collection


def test_mongodb_field_summary_normalizes_missing_null_types_and_lengths():
    stats = _summarize_fields(
        [
            {"value": None, "name": "é"},
            {"value": 2, "name": "hello", "a.b": 1, "a": {"b": 2}},
            {"value": float("nan"), "other": True},
        ]
    )

    assert stats["value"]["presence_rate"] == 1.0
    assert stats["value"]["null_rate"] == pytest.approx(1 / 3)
    assert stats["value"]["type_distribution"] == {"null": 1, "number": 2}
    assert stats["value"]["numeric_mean"] == 2.0
    assert stats["name"]["min_len"] == 1
    assert stats["name"]["max_len"] == 5
    assert stats["a\\.b"]["numeric_mean"] == 1.0
    assert stats["a.b"]["numeric_mean"] == 2.0

    with pytest.raises(ValueError, match="between 25 and 1000"):
        MongoDBConnector(
            {
                "uri": "mongodb://unused",
                "database": "analytics",
                "profile_sample_size": 1,
            }
        )._sample_size()


@pytest.mark.asyncio
async def test_mongodb_native_schema_and_profile_are_bounded_and_provenanced():
    connector, collection = _connector()

    schemas = await connector.discover_schemas()
    assert schemas[0].name == "analytics"
    assert schemas[0].tables[0].estimated_rows == 2**31 + 5

    ddl = await connector.get_table_ddl("analytics", "events")
    assert ddl.startswith('CREATE COLLECTION "analytics"."events"')
    assert '"nested.special field" string NULL' in ddl

    result = await ProfilerService().profile(
        connector,
        "analytics",
        "events",
        freshness_column="nested.event_at",
    )

    assert result.error is None
    assert result.row_count == 2**31 + 5
    assert result.freshness_seconds == pytest.approx(3600, abs=5)
    assert len(result.schema_fingerprint) == 64
    assert result.column_metrics["amount"]["null_rate"] == pytest.approx(1 / 3)
    assert result.column_metrics["amount"]["numeric_mean"] == pytest.approx(2.5)
    assert result.profile_provenance == {
        "profile_mode": "sampled_native",
        "connector": "mongodb",
        "count_mode": "estimated",
        "population_estimate": 2**31 + 5,
        "sample_strategy": "random_bounded",
        "sample_size": 3,
        "sample_limit": 100,
        "sampled_bytes": sum(collection.document_sizes),
        "sample_byte_budget": 8 * 1024 * 1024,
        "sample_byte_budget_exhausted": False,
        "document_byte_limit": 128 * 1024,
        "oversized_sampled_count": 0,
        "array_item_limit": 100,
        "schema_mode": "sampled",
        "field_limit": 500,
        "fields_truncated": False,
    }
    serialized = json.dumps(result.column_metrics)
    assert "customer@example.com" not in serialized
    assert "token-secret-value" not in serialized
    assert "sample_values" not in serialized
    for _pipeline, kwargs in collection.aggregate_calls:
        assert kwargs["allowDiskUse"] is False
        assert kwargs["maxTimeMS"] <= 30_000
        assert kwargs["batchSize"] == 16
        assert _pipeline[1]["$project"]["_datawatch_size"] == {"$bsonSize": "$$ROOT"}
    assert all(cursor.closed for cursor in collection.aggregate_cursors)


@pytest.mark.asyncio
async def test_mongodb_restricts_database_freshness_and_arbitrary_pipelines():
    connector, collection = _connector()

    with pytest.raises(ConnectorConfigurationError, match="configured database"):
        await connector.get_table_ddl("other", "events")

    collection.indexes = {}
    with pytest.raises(ConnectorConfigurationError, match="leading field"):
        await connector.validate_profile_config("analytics", "events", "event_at")

    failed_profile = await ProfilerService().profile(
        connector,
        "analytics",
        "events",
        freshness_column="event_at",
    )
    assert failed_profile.error == (
        "MongoDB freshness_column must be the leading field of an index."
    )

    with pytest.raises(NotImplementedError, match="caller-provided"):
        await connector.execute_profile_query(
            '{"pipeline":[{"$out":"exfiltrated"}]}'
        )

    system = MongoDBConnector(
        {"uri": "mongodb://unused", "database": "admin", "tls_mode": "disabled"}
    )
    with pytest.raises(ConnectorConfigurationError, match="system databases"):
        system._database_name()


@pytest.mark.asyncio
async def test_mongodb_rejects_partial_or_non_date_freshness_indexes():
    connector, collection = _connector()
    collection.indexes["freshness"]["partialFilterExpression"] = {
        "nested.event_at": {"$exists": True}
    }
    with pytest.raises(ConnectorConfigurationError, match="leading field"):
        await connector.validate_profile_config(
            "analytics", "events", "nested.event_at"
        )

    collection.indexes["freshness"].pop("partialFilterExpression")
    collection.freshness_rows = []
    with pytest.raises(ConnectorConfigurationError, match="scalar BSON date"):
        await connector.validate_profile_config(
            "analytics", "events", "nested.event_at"
        )


@pytest.mark.asyncio
async def test_mongodb_sampling_enforces_document_and_total_byte_budgets():
    documents = [{"value": index} for index in range(71)]
    sizes = [_MAX_PROFILE_DOCUMENT_BYTES] * 70 + [
        _MAX_PROFILE_DOCUMENT_BYTES + 1
    ]
    collection = _Collection(
        documents,
        document_count=len(documents),
        document_sizes=sizes,
    )
    connector = MongoDBConnector(
        {
            "uri": "mongodb://unused",
            "database": "analytics",
            "tls_mode": "disabled",
            "profile_sample_size": 100,
        }
    )
    connector._client = _Client(_Database(collection))

    stats = await connector.get_collection_stats("analytics", "events")

    assert stats["sample_size"] == 64
    assert stats["sampled_bytes"] == 8 * 1024 * 1024
    assert stats["sample_byte_budget_exhausted"] is True
    assert collection.aggregate_cursors[-1].closed is True


def test_mongodb_client_enforces_tls_timeouts_pool_and_stable_api(monkeypatch):
    captured = {}

    class ServerApi:
        def __init__(self, version, **kwargs):
            self.version = version
            self.kwargs = kwargs

    def async_mongo_client(uri, **kwargs):
        captured.update({"uri": uri, **kwargs})
        return object()

    monkeypatch.setitem(
        sys.modules,
        "pymongo",
        SimpleNamespace(AsyncMongoClient=async_mongo_client),
    )
    monkeypatch.setitem(
        sys.modules,
        "pymongo.server_api",
        SimpleNamespace(ServerApi=ServerApi),
    )
    connector = MongoDBConnector(
        {"uri": "mongodb://db.example.com/analytics", "database": "analytics"}
    )

    connector._get_client()

    assert captured["tls"] is True
    assert captured["tlsAllowInvalidCertificates"] is False
    assert captured["tlsAllowInvalidHostnames"] is False
    assert captured["serverSelectionTimeoutMS"] == 10_000
    assert captured["socketTimeoutMS"] == 30_000
    assert captured["maxPoolSize"] == 5
    assert captured["server_api"].version == "1"

    captured.clear()
    local = MongoDBConnector(
        {
            "uri": "mongodb://localhost:27018",
            "database": "analytics",
            "tls_mode": "disabled",
        }
    )
    local._get_client()
    assert captured["tls"] is False
    assert "tlsAllowInvalidCertificates" not in captured
    assert "tlsAllowInvalidHostnames" not in captured


@pytest.mark.asyncio
async def test_cassandra_never_executes_caller_provided_cql():
    connector = CassandraConnector({"hosts": "cassandra.example.com"})
    with pytest.raises(NotImplementedError, match="typed partition plan"):
        await connector.execute_profile_query("DELETE FROM ks.events")


def test_cassandra_requires_verified_tls_by_default(monkeypatch):
    connector = CassandraConnector({"hosts": "cassandra.example.com"})
    context = connector._ssl_context()
    assert context is not None
    assert context.check_hostname is True

    captured = {}

    class Cluster:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def connect(self, *_args):
            return object()

    monkeypatch.setitem(sys.modules, "cassandra.cluster", SimpleNamespace(Cluster=Cluster))
    monkeypatch.setitem(
        sys.modules,
        "cassandra.auth",
        SimpleNamespace(PlainTextAuthProvider=lambda **_kwargs: object()),
    )
    connector._connect_sync()

    assert captured["ssl_context"].check_hostname is True
    assert captured["ssl_options"] == {"server_hostname": "cassandra.example.com"}


@pytest.mark.asyncio
async def test_mongodb_container_connection_discovery_schema_and_native_profile():
    try:
        probe = socket.create_connection(("127.0.0.1", 27018), timeout=0.2)
        probe.close()
    except OSError:
        pytest.skip(
            "MongoDB test service unavailable; run docker compose -f "
            "docker-compose.test-dbs.yml up -d test-mongo"
        )

    connector = MongoDBConnector(
        {
            "uri": (
                "mongodb://datawatch-root:datawatch-root@127.0.0.1:27018/"
                "?authSource=admin"
            ),
            "database": "datawatch_nosql",
            "tls_mode": "disabled",  # isolated local conformance service only
            "profile_sample_size": 250,
        }
    )
    if not await connector.test_connection():
        await connector.close()
        pytest.skip(
            "MongoDB test service unavailable; run docker compose -f "
            "docker-compose.test-dbs.yml up -d test-mongo"
        )

    try:
        schemas = await connector.discover_schemas()
        database = next(schema for schema in schemas if schema.name == "datawatch_nosql")
        assert any(table.name == "events" for table in database.tables)

        ddl = await connector.get_table_ddl("datawatch_nosql", "events")
        assert '"metadata.browser" string NOT NULL' in ddl

        result = await ProfilerService().profile(
            connector,
            "datawatch_nosql",
            "events",
            freshness_column="occurred_at",
        )
        assert result.error is None
        assert result.row_count == 250
        assert result.profile_provenance["count_mode"] == "estimated"
        assert result.profile_provenance["sample_size"] == 250
        assert result.column_metrics["metadata.browser"]["presence_rate"] == 1.0
        assert result.freshness_seconds is not None
    finally:
        await connector.close()
