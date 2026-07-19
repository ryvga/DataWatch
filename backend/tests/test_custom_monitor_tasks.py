import uuid
from types import SimpleNamespace

import pytest


@pytest.mark.asyncio
async def test_custom_monitors_roll_back_after_sql_error(monkeypatch):
    from app import database
    from app.connectors import factory
    from app.services import crypto, incident
    from app.tasks import _run_custom_monitors_async

    org_id = uuid.uuid4()
    table_id = uuid.uuid4()
    source_id = uuid.uuid4()
    table = SimpleNamespace(
        id=table_id,
        source_id=source_id,
        schema_name="public",
        table_name="events",
    )
    source = SimpleNamespace(
        id=source_id,
        org_id=org_id,
        type="postgres",
        connection_config={"encrypted": "encrypted"},
    )
    monitors = [
        SimpleNamespace(
            id=uuid.uuid4(),
            name="Broken query",
            sql_query="SELECT missing_column FROM public.events",
            severity="P3",
            last_run_at=None,
            last_result=None,
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            name="Valid query",
            sql_query=(
                "SELECT COUNT(*) AS violation_count "
                "FROM public.events WHERE false"
            ),
            severity="P3",
            last_run_at=None,
            last_result=None,
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            name="Empty result",
            sql_query=(
                "SELECT COUNT(*) AS violation_count "
                "FROM public.events WHERE status = 'empty-result'"
            ),
            severity="P3",
            last_run_at=None,
            last_result=None,
        ),
    ]

    class FakeScalars:
        def all(self):
            return monitors

    class FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, model, item_id):
            if model.__name__ == "MonitoredTable":
                return table
            if model.__name__ == "DataSource":
                return source
            return None

        async def scalars(self, stmt):
            return FakeScalars()

        def add(self, item):
            self.added.append(item)

        async def commit(self):
            self.committed = True

    class FakeConnection:
        def __init__(self, connector):
            self.connector = connector
            self.rollback_calls = 0
            self.closed = False

        async def rollback(self):
            self.rollback_calls += 1
            self.connector.aborted = False

    class FakeConnector:
        def __init__(self):
            self.aborted = False
            self.closed = False
            self._conn = FakeConnection(self)

        async def execute_monitor_query(self, query, *, timeout_seconds):
            if "missing_column" in query:
                self.aborted = True
                raise RuntimeError("column missing_column does not exist")
            if self.aborted:
                raise RuntimeError("current transaction is aborted")
            if "empty-result" in query:
                return {}
            return {"violation_count": 0}

        async def close(self):
            self.closed = True

    class FakeIncidentService:
        async def auto_resolve(self, db, table, check_results):
            return None

        async def create_or_update(self, db, org_id, table, failed_checks, profile_id):
            return None

    fake_session = FakeSession()
    connector = FakeConnector()
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(crypto, "decrypt_config", lambda encrypted, org_id: {})
    monkeypatch.setattr(factory.ConnectorFactory, "create", lambda source_type, config: connector)
    monkeypatch.setattr(incident, "IncidentService", FakeIncidentService)

    result = await _run_custom_monitors_async(str(table_id))

    assert result == {"status": "ok", "run": 1, "failed": 0}
    assert connector._conn.rollback_calls == 2
    assert monitors[0].last_result["error"] == "column missing_column does not exist"
    assert monitors[1].last_result["passed"] is True
    assert "exactly one row" in monitors[2].last_result["error"]
    assert fake_session.committed is True
