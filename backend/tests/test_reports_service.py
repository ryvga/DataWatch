from datetime import UTC, datetime, timedelta
import uuid

import pytest

from app.models import CheckResult, DataSource, Incident, MonitoredTable, Organization, TableProfile
from app.services.reports import ReportService


@pytest.mark.asyncio
async def test_generate_weekly_report_summarizes_org_activity(db_session):
    org_id = uuid.uuid4()
    now = datetime.now(UTC)
    org = Organization(id=org_id, name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}")
    source = DataSource(
        id=uuid.uuid4(),
        org_id=org_id,
        name="Warehouse",
        type="postgres",
        connection_config={},
        status="connected",
    )
    orders = MonitoredTable(
        id=uuid.uuid4(),
        source_id=source.id,
        schema_name="public",
        table_name="orders",
        last_profiled_at=now - timedelta(hours=1),
    )
    users = MonitoredTable(
        id=uuid.uuid4(),
        source_id=source.id,
        schema_name="public",
        table_name="users",
        last_profiled_at=now - timedelta(hours=2),
    )
    db_session.add_all([org, source, orders, users])
    await db_session.flush()

    db_session.add_all(
        [
            Incident(
                org_id=org_id,
                table_id=orders.id,
                severity="P1",
                status="open",
                title="Orders stopped",
                created_at=now - timedelta(days=1),
            ),
            Incident(
                org_id=org_id,
                table_id=users.id,
                severity="P3",
                status="resolved",
                title="Null spike",
                created_at=now - timedelta(days=2),
                resolved_at=now - timedelta(days=1),
            ),
            Incident(
                org_id=org_id,
                table_id=orders.id,
                severity="P2",
                status="resolved",
                title="Old incident",
                created_at=now - timedelta(days=10),
            ),
            CheckResult(
                table_id=orders.id,
                check_type="freshness",
                check_name="Freshness SLA",
                status="failed",
                checked_at=now - timedelta(hours=3),
            ),
            CheckResult(
                table_id=orders.id,
                check_type="freshness",
                check_name="Freshness SLA",
                status="failed",
                checked_at=now - timedelta(hours=2),
            ),
            CheckResult(
                table_id=orders.id,
                check_type="schema",
                check_name="Schema Drift",
                status="passed",
                checked_at=now - timedelta(hours=2),
            ),
            CheckResult(
                table_id=users.id,
                check_type="row_count",
                check_name="Row Count",
                status="passed",
                checked_at=now - timedelta(hours=1),
            ),
        ]
    )
    await db_session.flush()

    report = await ReportService.generate_weekly_report(org_id, db_session)

    assert report["report_type"] == "weekly"
    assert report["org_id"] == org_id
    assert report["window_days"] == 7
    assert report["incidents_total"] == 2
    assert report["incidents_open"] == 1
    assert report["incidents_resolved"] == 1
    assert report["incidents_by_severity"] == {"P1": 1, "P3": 1}
    assert report["checks_total"] == 4
    assert report["checks_passed"] == 2
    assert report["checks_failed"] == 2
    assert report["checks_by_type"] == {"freshness": 2, "schema": 1, "row_count": 1}
    assert report["tables_monitored"] == 2
    assert report["tables_with_incidents"] == ["orders", "users"]
    assert report["top_failing_checks"] == [{"check_name": "Freshness SLA", "count": 2}]
    assert report["ai_summary"] == "AI summary pending"
    assert report["health_grade"] in {"A", "B", "C", "D", "F"}
    assert any("open incident" in item.lower() for item in report["recommendations"])


@pytest.mark.asyncio
async def test_generate_incident_report_loads_context_and_debug_queries(db_session):
    org_id = uuid.uuid4()
    now = datetime.now(UTC)
    org = Organization(id=org_id, name="Beta", slug=f"beta-{uuid.uuid4().hex[:8]}")
    source = DataSource(
        id=uuid.uuid4(),
        org_id=org_id,
        name="Analytics DB",
        type="postgres",
        connection_config={},
        status="connected",
    )
    table = MonitoredTable(
        id=uuid.uuid4(),
        source_id=source.id,
        schema_name="analytics",
        table_name="payments",
    )
    db_session.add_all([org, source, table])
    await db_session.flush()

    older_profile = TableProfile(
        table_id=table.id,
        collected_at=now - timedelta(hours=2),
        row_count=1200,
        freshness_seconds=120.0,
        schema_fingerprint="old",
        column_metrics={"amount": {"null_rate": 0.01}},
    )
    latest_profile = TableProfile(
        table_id=table.id,
        collected_at=now - timedelta(hours=1),
        row_count=0,
        freshness_seconds=7200.0,
        schema_fingerprint="new",
        column_metrics={"amount": {"null_rate": 0.4}},
    )
    incident = Incident(
        id=uuid.uuid4(),
        org_id=org_id,
        table_id=table.id,
        severity="P1",
        status="open",
        title="Payments stopped",
        fired_checks=["row_count_zero"],
        llm_narration={"summary": "Payments stopped loading after the nightly job failed."},
        created_at=now - timedelta(minutes=30),
    )
    db_session.add_all(
        [
            older_profile,
            latest_profile,
            incident,
            CheckResult(
                table_id=table.id,
                profile_id=latest_profile.id,
                check_type="row_count",
                check_name="Row Count Zero",
                status="failed",
                observed_value=0,
                checked_at=now - timedelta(minutes=30),
            ),
        ]
    )
    await db_session.flush()

    report = await ReportService.generate_incident_report(incident.id, db_session)

    assert report["report_type"] == "incident"
    assert report["incident_id"] == incident.id
    assert report["severity"] == "P1"
    assert report["status"] == "open"
    assert report["table_name"] == "payments"
    assert report["source_name"] == "Analytics DB"
    assert report["detected_at"] == incident.created_at
    assert report["resolved_at"] is None
    assert report["llm_narration"] == incident.llm_narration
    assert report["client_safe_summary"] == "Payments stopped loading after the nightly job failed."
    assert report["fired_checks"][0]["check_name"] == "Row Count Zero"
    assert [snapshot["row_count"] for snapshot in report["profile_snapshots"]] == [0, 1200]
    assert any("analytics.payments" in query for query in report["debug_queries"])
