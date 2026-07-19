from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.connectors.factory import CONNECTOR_REGISTRY
from app.routers import sources
from app.routers import tables


@pytest.mark.asyncio
async def test_connector_types_include_registry_fields_and_versions():
    metadata = await sources.get_connector_types()

    assert {item["type"] for item in metadata} == set(CONNECTOR_REGISTRY)
    for item in metadata:
        assert item["label"]
        assert item["description"]
        assert isinstance(item["fields"], list)
        assert item["versions"]
        assert item["readiness"] in {"stable", "beta", "experimental", "planned"}
        assert item["capabilities"]["profiling"] in {"none", "core", "full"}
        assert item["capabilities"]["custom_monitors"] in {
            "none",
            "sql_scalar",
            "partition_count",
        }
        field_names = {field["name"] for field in item["fields"]}
        assert set(item["required"]).issubset(field_names)

    by_type = {item["type"]: item for item in metadata}
    assert by_type["postgres"]["capabilities"]["profiling"] == "full"
    assert by_type["sqlite"]["capabilities"]["profiling"] == "core"
    assert by_type["mongodb"]["capabilities"]["profiling"] == "none"
    assert by_type["snowflake"]["readiness"] == "planned"


@pytest.mark.asyncio
async def test_preview_source_connection_tests_unsaved_config(monkeypatch):
    calls = {}

    class FakeConnector:
        async def test_connection(self):
            return True

        async def close(self):
            calls["closed"] = True

    monkeypatch.setattr(
        sources.ConnectorFactory,
        "create",
        lambda source_type, config: calls.setdefault("args", (source_type, config)) and FakeConnector(),
    )

    result = await sources.preview_source_connection(
        sources.DataSourceTestRequest(
            type="postgres",
            connection_config={"host": "localhost", "database": "demo"},
        )
    )

    assert result.connected is True
    assert result.error is None
    assert result.latency_ms >= 0
    assert calls["args"] == ("postgres", {"host": "localhost", "database": "demo"})
    assert calls["closed"] is True


@pytest.mark.asyncio
async def test_get_source_table_schema_returns_connector_ddl(monkeypatch):
    calls = {}
    source = SimpleNamespace(
        id="source-1",
        type="postgres",
        connection_config={"encrypted": "ciphertext"},
    )

    class FakeConnector:
        async def get_table_ddl(self, schema_name, table_name):
            calls["table"] = (schema_name, table_name)
            return "CREATE TABLE public.orders (id integer, updated_at timestamp);"

        async def close(self):
            calls["closed"] = True

    async def fake_get_source_or_404(source_id, org, db):
        calls["source"] = (source_id, org, db)
        return source

    monkeypatch.setattr(sources, "_get_source_or_404", fake_get_source_or_404)
    monkeypatch.setattr(sources, "decrypt_config", lambda encrypted, org_id: {"host": "db"})
    monkeypatch.setattr(sources.ConnectorFactory, "create", lambda source_type, config: FakeConnector())

    result = await sources.get_source_table_schema(
        source_id="source-1",
        schema_name="public",
        table_name="orders",
        org=SimpleNamespace(id="org-1"),
        db=object(),
    )

    assert result["source_id"] == "source-1"
    assert result["schema_name"] == "public"
    assert result["table_name"] == "orders"
    assert "updated_at timestamp" in result["ddl"]
    assert calls["table"] == ("public", "orders")
    assert calls["closed"] is True


@pytest.mark.asyncio
async def test_get_schemas_checks_ownership_before_tenant_scoped_cache(monkeypatch):
    calls = []

    class FakeRedis:
        async def get(self, key):
            calls.append(("cache", key))
            return '{"schemas": []}'

        async def aclose(self):
            return None

    async def fake_get_source_or_404(source_id, org, db):
        calls.append(("ownership", source_id, org.id))
        return SimpleNamespace(id=source_id)

    async def fake_redis():
        return FakeRedis()

    monkeypatch.setattr(sources, "_get_source_or_404", fake_get_source_or_404)
    monkeypatch.setattr(sources, "_redis", fake_redis)

    result = await sources.get_schemas(
        source_id="source-1",
        org=SimpleNamespace(id="org-7"),
        db=object(),
    )

    assert result.schemas == []
    assert calls == [
        ("ownership", "source-1", "org-7"),
        ("cache", "discovery:org-7:source-1"),
    ]


@pytest.mark.asyncio
async def test_discovery_cache_invalidation_is_tenant_scoped_and_closes(monkeypatch):
    calls = []

    class FakeRedis:
        async def delete(self, key):
            calls.append(("delete", key))

        async def aclose(self):
            calls.append(("close",))

    async def fake_redis():
        return FakeRedis()

    monkeypatch.setattr(sources, "_redis", fake_redis)

    await sources._invalidate_discovery_cache("org-2", "source-9")

    assert calls == [
        ("delete", "discovery:org-2:source-9"),
        ("close",),
    ]


@pytest.mark.asyncio
async def test_create_table_rejects_connector_without_profile_capability(monkeypatch):
    async def fake_resolve(source_id, org, db):
        return SimpleNamespace(id=source_id, type="mongodb")

    monkeypatch.setattr(tables, "_resolve_org_from_source", fake_resolve)

    with pytest.raises(HTTPException) as exc_info:
        await tables.create_table(
            body=tables.TableCreate(
                source_id="source-1",
                schema_name="analytics",
                table_name="events",
            ),
            org=SimpleNamespace(id="org-1"),
            db=object(),
        )

    assert exc_info.value.status_code == 422
    assert "not scheduled profiling" in exc_info.value.detail


@pytest.mark.asyncio
async def test_pause_source_archives_source_and_deactivates_tables(monkeypatch):
    source = SimpleNamespace(id="source-1", status="connected")
    tables = [
        SimpleNamespace(id="table-1", is_active=True),
        SimpleNamespace(id="table-2", is_active=True),
    ]
    removed_jobs = []
    invalidated = []

    class ScalarResult:
        def all(self):
            return tables

    class FakeSession:
        async def scalar(self, _query):
            return source

        async def scalars(self, _query):
            return ScalarResult()

        async def commit(self):
            return None

    monkeypatch.setattr("app.scheduler.remove_table_job", lambda table_id: removed_jobs.append(table_id))
    async def fake_invalidate(org_id, source_id):
        invalidated.append((org_id, source_id))

    monkeypatch.setattr(sources, "_invalidate_discovery_cache", fake_invalidate)

    await sources.pause_source(
        source_id="source-1",
        org=SimpleNamespace(id="org-1"),
        db=FakeSession(),
    )

    assert source.status == "paused"
    assert [table.is_active for table in tables] == [False, False]
    assert removed_jobs == ["table-1", "table-2"]
    assert invalidated == [("org-1", "source-1")]
