from types import SimpleNamespace

import pytest

from app.connectors.factory import CONNECTOR_REGISTRY
from app.routers import sources


@pytest.mark.asyncio
async def test_connector_types_include_registry_fields_and_versions():
    metadata = await sources.get_connector_types()

    assert {item["type"] for item in metadata} == set(CONNECTOR_REGISTRY)
    for item in metadata:
        assert item["label"]
        assert item["description"]
        assert isinstance(item["fields"], list)
        assert item["versions"]
        field_names = {field["name"] for field in item["fields"]}
        assert set(item["required"]).issubset(field_names)


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

