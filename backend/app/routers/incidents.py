from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.data_source import DataSource
from app.models.incident import Incident
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.routers.auth import get_current_org_from_jwt

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class IncidentResponse(BaseModel):
    id: str
    table_id: str
    severity: str
    status: str
    title: str
    fired_checks: list | None
    llm_narration: dict | None
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_incident_or_404(
    incident_id: str, org: Organization, db: AsyncSession
) -> Incident:
    incident = await db.scalar(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.org_id == org.id,
        )
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


def _incident_response(i: Incident) -> IncidentResponse:
    return IncidentResponse(
        id=str(i.id),
        table_id=str(i.table_id),
        severity=i.severity,
        status=i.status,
        title=i.title,
        fired_checks=i.fired_checks,
        llm_narration=i.llm_narration,
        created_at=i.created_at,
        acknowledged_at=i.acknowledged_at,
        resolved_at=i.resolved_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    table_id: str | None = None,
    limit: int = 50,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    q = select(Incident).where(Incident.org_id == org.id)

    if status:
        q = q.where(Incident.status == status)
    if severity:
        q = q.where(Incident.severity == severity.upper())
    if table_id:
        q = q.where(Incident.table_id == table_id)

    q = q.order_by(desc(Incident.created_at)).limit(min(limit, 250))
    incidents = (await db.scalars(q)).all()
    return [_incident_response(i) for i in incidents]


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    return _incident_response(await _get_incident_or_404(incident_id, org, db))


@router.patch("/{incident_id}/acknowledge", response_model=IncidentResponse)
async def acknowledge_incident(
    incident_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timezone
    incident = await _get_incident_or_404(incident_id, org, db)
    if incident.status in ("resolved", "acknowledged", "investigating"):
        raise HTTPException(status_code=409, detail=f"Incident is already {incident.status}")
    incident.status = "acknowledged"
    incident.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    return _incident_response(incident)


@router.patch("/{incident_id}/investigate", response_model=IncidentResponse)
async def investigate_incident(
    incident_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Mark incident as actively being investigated (ack → investigating)."""
    from datetime import timezone
    incident = await _get_incident_or_404(incident_id, org, db)
    if incident.status == "resolved":
        raise HTTPException(status_code=409, detail="Incident already resolved")
    incident.status = "investigating"
    if not incident.acknowledged_at:
        incident.acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    return _incident_response(incident)


@router.patch("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(
    incident_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timezone
    incident = await _get_incident_or_404(incident_id, org, db)
    if incident.status == "resolved":
        raise HTTPException(status_code=409, detail="Incident already resolved")
    incident.status = "resolved"
    incident.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return _incident_response(incident)


class MuteRequest(BaseModel):
    hours: int = 24

@router.patch("/{incident_id}/mute", response_model=IncidentResponse)
async def mute_incident(
    incident_id: str,
    body: MuteRequest = MuteRequest(),
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Mute an incident for N hours (default 24). Prevents re-creation during mute window."""
    from datetime import timezone, timedelta
    incident = await _get_incident_or_404(incident_id, org, db)
    if incident.status == "resolved":
        raise HTTPException(status_code=409, detail="Incident already resolved")
    incident.status = "muted"
    # Store mute expiry in llm_narration.muted_until (no schema change needed)
    narration = dict(incident.llm_narration or {})
    muted_until = (datetime.now(timezone.utc) + timedelta(hours=body.hours)).isoformat()
    narration["muted_until"] = muted_until
    narration["muted_hours"] = body.hours
    incident.llm_narration = narration
    await db.commit()
    return _incident_response(incident)


@router.patch("/{incident_id}/false-positive", response_model=IncidentResponse)
async def mark_false_positive(
    incident_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Mark as false positive (ignored). Helps train future detection thresholds."""
    incident = await _get_incident_or_404(incident_id, org, db)
    if incident.status in ("resolved", "ignored"):
        raise HTTPException(status_code=409, detail=f"Incident already {incident.status}")
    incident.status = "ignored"
    if not incident.title.startswith("[FP]"):
        incident.title = f"[FP] {incident.title}"
    await db.commit()
    return _incident_response(incident)


@router.get("/stats")
async def get_incident_stats(
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Quick stats for dashboard — open/ack/investigating/resolved counts."""
    from sqlalchemy import func
    from datetime import timezone, timedelta
    from app.models.incident import Incident
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    rows = (await db.execute(
        select(Incident.status, func.count().label("n"))
        .where(Incident.org_id == org.id)
        .group_by(Incident.status)
    )).all()
    counts = {r.status: r.n for r in rows}
    p1_open = await db.scalar(
        select(func.count()).where(Incident.org_id == org.id, Incident.status == "open", Incident.severity == "P1")
    ) or 0
    resolved_7d = await db.scalar(
        select(func.count()).where(Incident.org_id == org.id, Incident.status == "resolved", Incident.resolved_at >= week_ago)
    ) or 0
    return {
        "open": counts.get("open", 0),
        "acknowledged": counts.get("acknowledged", 0),
        "investigating": counts.get("investigating", 0),
        "muted": counts.get("muted", 0),
        "resolved_7d": resolved_7d,
        "p1_open": p1_open,
        "total_open": counts.get("open", 0) + counts.get("acknowledged", 0) + counts.get("investigating", 0),
    }


@router.post("/{incident_id}/narration/retry", response_model=IncidentResponse)
async def retry_narration(
    incident_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Clear a failed narration and re-queue LLM generation."""
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.llm import invalidate_narration_cache
    from app.tasks import generate_llm_narration

    incident = await _get_incident_or_404(incident_id, org, db)

    # Clear the failed narration so the task doesn't see a cache hit
    incident.llm_narration = None
    flag_modified(incident, "llm_narration")
    await db.commit()
    await db.refresh(incident)

    # Clear Redis cache entry
    invalidate_narration_cache(incident_id)

    # Re-queue the Celery task
    generate_llm_narration.delay(incident_id)

    return _incident_response(incident)
