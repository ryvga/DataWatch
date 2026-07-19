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
            "legacy_sql_scalar",
        }
        assert item["capabilities"]["compiled_monitors"] in {
            "none",
            "internal_read_only",
        }
        field_names = {field["name"] for field in item["fields"]}
        assert set(item["required"]).issubset(field_names)

    by_type = {item["type"]: item for item in metadata}
    assert by_type["postgres"]["capabilities"]["profiling"] == "full"
    assert by_type["postgres"]["capabilities"]["compiled_monitors"] == (
        "internal_read_only"
    )
    assert by_type["sqlite"]["capabilities"]["profiling"] == "core"
    assert by_type["mysql"]["capabilities"]["profiling"] == "core"
    assert by_type["sqlserver"]["capabilities"]["profiling"] == "core"
    mysql_fields = {
        field["name"]: field for field in by_type["mysql"]["fields"]
    }
    assert mysql_fields["tls_mode"]["default"] == "verify_identity"
    assert mysql_fields["tls_mode"]["options"] == ["verify_identity", "disabled"]
    assert by_type["mongodb"]["capabilities"]["profiling"] == "core"
    assert by_type["mongodb"]["capabilities"]["sampling"] is True
    assert "database" in by_type["mongodb"]["required"]
    cassandra_fields = {
        field["name"]: field for field in by_type["cassandra"]["fields"]
    }
    assert cassandra_fields["tls_mode"]["default"] == "verify_identity"
    assert "Astra DB" not in by_type["cassandra"]["versions"]
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
async def test_connection_errors_never_echo_driver_or_credential_details(monkeypatch):
    class FailingConnector:
        async def test_connection(self):
            raise RuntimeError("access denied password=super-secret host=internal-db")

        async def close(self):
            return None

    monkeypatch.setattr(
        sources.ConnectorFactory,
        "create",
        lambda source_type, config: FailingConnector(),
    )

    result = await sources._test_connection_config(
        "postgres",
        {"host": "internal-db", "database": "analytics", "password": "super-secret"},
    )

    assert result.connected is False
    assert result.error == "Database authentication failed. Check the configured credentials."
    assert "super-secret" not in result.error
    assert "internal-db" not in result.error


@pytest.mark.asyncio
async def test_connection_preview_swallows_and_sanitizes_close_failures(monkeypatch):
    class Connector:
        async def test_connection(self):
            return True

        async def close(self):
            raise RuntimeError("password=super-secret host=internal-db")

    monkeypatch.setattr(
        sources.ConnectorFactory,
        "create",
        lambda source_type, config: Connector(),
    )

    result = await sources._test_connection_config(
        "postgres",
        {"host": "internal-db", "database": "analytics"},
    )

    assert result.connected is True
    assert result.error is None


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
async def test_create_table_rejects_cassandra_without_profile_capability(monkeypatch):
    async def fake_resolve(source_id, org, db):
        return SimpleNamespace(id=source_id, type="cassandra")

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
async def test_create_table_fails_closed_when_schema_introspection_fails(monkeypatch):
    source = SimpleNamespace(
        id="source-1",
        type="postgres",
        connection_config={"encrypted": "ciphertext"},
    )

    class FailingConnector:
        async def get_table_ddl(self, schema, table):
            raise RuntimeError("password=super-secret host=internal-db")

        async def close(self):
            return None

    class FakeSession:
        async def scalar(self, query):
            return None

    async def fake_resolve(source_id, org, db):
        return source

    async def allow_table_limit(org, db):
        return None

    monkeypatch.setattr(tables, "_resolve_org_from_source", fake_resolve)
    monkeypatch.setattr(tables, "decrypt_config", lambda encrypted, org_id: {})
    monkeypatch.setattr(tables.ConnectorFactory, "create", lambda source_type, config: FailingConnector())
    monkeypatch.setattr("app.services.plans.enforce_table_limit", allow_table_limit)

    with pytest.raises(HTTPException) as exc_info:
        await tables.create_table(
            body=tables.TableCreate(
                source_id="source-1",
                schema_name="public",
                table_name="orders",
            ),
            org=SimpleNamespace(id="org-1"),
            db=FakeSession(),
        )

    assert exc_info.value.status_code == 422
    assert "super-secret" not in exc_info.value.detail
    assert "internal-db" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_table_rejects_caller_owned_schema_snapshot(monkeypatch):
    source = SimpleNamespace(id="source-1", type="postgres")

    class FakeSession:
        async def scalar(self, query):
            return None

    async def fake_resolve(source_id, org, db):
        return source

    async def allow_table_limit(org, db):
        return None

    monkeypatch.setattr(tables, "_resolve_org_from_source", fake_resolve)
    monkeypatch.setattr("app.services.plans.enforce_table_limit", allow_table_limit)

    with pytest.raises(HTTPException) as exc_info:
        await tables.create_table(
            body=tables.TableCreate(
                source_id="source-1",
                schema_name="public",
                table_name="orders",
                dbt_model_yaml="CREATE TABLE forged.orders (id integer NOT NULL);",
            ),
            org=SimpleNamespace(id="org-1"),
            db=FakeSession(),
        )
    assert exc_info.value.status_code == 422
    assert "captured from the source" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_table_validates_freshness_against_live_schema(monkeypatch):
    source = SimpleNamespace(
        id="source-1",
        type="postgres",
        connection_config={"encrypted": "ciphertext"},
    )

    class Connector:
        async def get_table_ddl(self, schema, table):
            return "CREATE TABLE public.orders (\n  id integer NOT NULL\n);"

        async def close(self):
            return None

    class FakeSession:
        async def scalar(self, query):
            return None

    async def fake_resolve(source_id, org, db):
        return source

    async def allow_table_limit(org, db):
        return None

    monkeypatch.setattr(tables, "_resolve_org_from_source", fake_resolve)
    monkeypatch.setattr(tables, "decrypt_config", lambda encrypted, org_id: {})
    monkeypatch.setattr(
        tables.ConnectorFactory, "create", lambda source_type, config: Connector()
    )
    monkeypatch.setattr("app.services.plans.enforce_table_limit", allow_table_limit)

    with pytest.raises(HTTPException) as exc_info:
        await tables.create_table(
            body=tables.TableCreate(
                source_id="source-1",
                schema_name="public",
                table_name="orders",
                freshness_column="created_at",
            ),
            org=SimpleNamespace(id="org-1"),
            db=FakeSession(),
        )

    assert exc_info.value.status_code == 422
    assert "freshness_column" in exc_info.value.detail


@pytest.mark.asyncio
async def test_update_table_cannot_replace_or_bypass_live_schema(monkeypatch):
    monitored = SimpleNamespace(
        id="table-1",
        source_id="source-1",
        schema_name="public",
        table_name="orders",
        dbt_model_yaml="CREATE TABLE public.orders (\n  id integer NOT NULL\n);",
    )
    source = SimpleNamespace(
        id="source-1",
        type="postgres",
        connection_config={"encrypted": "ciphertext"},
    )

    class Connector:
        async def get_table_ddl(self, schema, table):
            return "CREATE TABLE public.orders (\n  id integer NOT NULL\n);"

        async def close(self):
            return None

    class FakeSession:
        async def get(self, model, object_id):
            return source

    async def fake_get_table(table_id, org, db):
        return monitored

    monkeypatch.setattr(tables, "_get_table_or_404", fake_get_table)
    monkeypatch.setattr(tables, "decrypt_config", lambda encrypted, org_id: {})
    monkeypatch.setattr(
        tables.ConnectorFactory, "create", lambda source_type, config: Connector()
    )

    with pytest.raises(HTTPException, match="read-only"):
        await tables.update_table(
            "table-1",
            tables.TableUpdate(dbt_model_yaml="CREATE TABLE forged.t (id int);"),
            SimpleNamespace(id="org-1"),
            FakeSession(),
        )

    with pytest.raises(HTTPException) as exc_info:
        await tables.update_table(
            "table-1",
            tables.TableUpdate(freshness_column="created_at"),
            SimpleNamespace(id="org-1"),
            FakeSession(),
        )
    assert exc_info.value.status_code == 422
    assert "freshness_column" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verified_schema_uses_native_document_field_binding(monkeypatch):
    source = SimpleNamespace(
        type="mongodb",
        connection_config={"encrypted": "ciphertext"},
    )
    validated = []

    class Connector:
        async def get_table_schema(self, schema, table):
            return "NATIVE SNAPSHOT (not relational DDL)", {"nested.event_at"}

        async def validate_profile_config(self, schema, table, freshness_column):
            validated.append((schema, table, freshness_column))

        async def close(self):
            return None

    monkeypatch.setattr(tables, "decrypt_config", lambda encrypted, org_id: {})
    monkeypatch.setattr(
        tables.ConnectorFactory,
        "create",
        lambda source_type, config: Connector(),
    )

    snapshot, columns = await tables._verified_schema_snapshot(
        source,
        "org-1",
        "analytics",
        "events",
        "nested.event_at",
    )

    assert snapshot == "NATIVE SNAPSHOT (not relational DDL)"
    assert columns == {"nested.event_at"}
    assert validated == [("analytics", "events", "nested.event_at")]


@pytest.mark.asyncio
async def test_verified_schema_allows_empty_native_collection(monkeypatch):
    source = SimpleNamespace(
        type="mongodb",
        connection_config={"encrypted": "ciphertext"},
    )

    class Connector:
        native_profile_kind = "document"

        async def get_table_schema(self, schema, table):
            return 'CREATE COLLECTION "analytics"."empty" (\n\n);', set()

        async def validate_profile_config(self, schema, table, freshness_column):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(tables, "decrypt_config", lambda encrypted, org_id: {})
    monkeypatch.setattr(
        tables.ConnectorFactory,
        "create",
        lambda source_type, config: Connector(),
    )

    snapshot, columns = await tables._verified_schema_snapshot(
        source,
        "org-1",
        "analytics",
        "empty",
        None,
    )

    assert snapshot.startswith("CREATE COLLECTION")
    assert columns == set()


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
