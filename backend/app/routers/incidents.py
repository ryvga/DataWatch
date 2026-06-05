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
    if incident.status != "open":
        raise HTTPException(status_code=409, detail=f"Incident is already {incident.status}")
    incident.status = "acknowledged"
    incident.acknowledged_at = datetime.now(timezone.utc)
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
    return _incident_response(incident)


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
