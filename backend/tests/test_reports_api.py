from types import SimpleNamespace

import pytest

from app.routers.reports import get_incident_report, get_weekly_report


@pytest.mark.asyncio
async def test_weekly_report_route_delegates_to_report_service(monkeypatch):
    calls = {}

    async def fake_generate_weekly_report(org_id, db, window_days=7):
        calls["args"] = (org_id, db, window_days)
        return {"report_type": "weekly", "window_days": window_days}

    monkeypatch.setattr(
        "app.services.reports.ReportService.generate_weekly_report",
        fake_generate_weekly_report,
    )
    db = object()

    response = await get_weekly_report(
        window_days=14,
        org=SimpleNamespace(id="org-1"),
        db=db,
    )

    assert response == {"report_type": "weekly", "window_days": 14}
    assert calls["args"] == ("org-1", db, 14)


@pytest.mark.asyncio
async def test_incident_report_route_delegates_to_report_service(monkeypatch):
    calls = {}

    async def fake_scalar(query):
        return SimpleNamespace(id="incident-1")

    async def fake_generate_incident_report(incident_id, db):
        calls["args"] = (incident_id, db)
        return {"report_type": "incident", "incident_id": incident_id}

    monkeypatch.setattr(
        "app.services.reports.ReportService.generate_incident_report",
        fake_generate_incident_report,
    )
    db = SimpleNamespace(scalar=fake_scalar)

    response = await get_incident_report(
        incident_id="incident-1",
        org=SimpleNamespace(id="org-1"),
        db=db,
    )

    assert response == {"report_type": "incident", "incident_id": "incident-1"}
    assert calls["args"] == ("incident-1", db)
