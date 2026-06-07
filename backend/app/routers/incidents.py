from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.incident import Incident
from app.models.organization import Organization
from app.models.team import Team
from app.models.user import User
from app.routers.auth import get_current_org_from_jwt, get_current_user_from_jwt

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
    # Assignment fields
    assignee_id: str | None
    assigned_team_id: str | None
    assignee_name: str | None
    assigned_team_name: str | None
    acknowledged_by_id: str | None
    resolved_by_id: str | None


class AssignIncidentBody(BaseModel):
    assignee_id: str | None = None
    assigned_team_id: str | None = None


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


async def _incident_response(i: Incident, db: AsyncSession) -> IncidentResponse:
    assignee_name: str | None = None
    assigned_team_name: str | None = None

    if getattr(i, "assignee_id", None):
        u = await db.get(User, i.assignee_id)
        if u:
            assignee_name = getattr(u, "full_name", None) or u.email

    if getattr(i, "assigned_team_id", None):
        t = await db.get(Team, i.assigned_team_id)
        if t:
            assigned_team_name = t.name

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
        resolved_at=getattr(i, "resolved_at", None),
        assignee_id=str(i.assignee_id) if getattr(i, "assignee_id", None) else None,
        assigned_team_id=str(i.assigned_team_id) if getattr(i, "assigned_team_id", None) else None,
        assignee_name=assignee_name,
        assigned_team_name=assigned_team_name,
        acknowledged_by_id=str(i.acknowledged_by_id) if getattr(i, "acknowledged_by_id", None) else None,
        resolved_by_id=str(i.resolved_by_id) if getattr(i, "resolved_by_id", None) else None,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    table_id: str | None = None,
    assigned_team_id: str | None = Query(None),
    assignee_id: str | None = Query(None),
    assigned_to_me: bool = Query(False),
    limit: int = 50,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    q = select(Incident).where(Incident.org_id == org.id)

    if status:
        q = q.where(Incident.status == status)
    if severity:
        q = q.where(Incident.severity == severity.upper())
    if table_id:
        q = q.where(Incident.table_id == table_id)
    if assigned_team_id:
        q = q.where(Incident.assigned_team_id == assigned_team_id)
    if assignee_id:
        q = q.where(Incident.assignee_id == assignee_id)
    if assigned_to_me:
        q = q.where(Incident.assignee_id == user.id)

    q = q.order_by(desc(Incident.created_at)).limit(min(limit, 250))
    incidents = (await db.scalars(q)).all()
    return [await _incident_response(i, db) for i in incidents]


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    incident = await _get_incident_or_404(incident_id, org, db)
    return await _incident_response(incident, db)


@router.patch("/{incident_id}/acknowledge", response_model=IncidentResponse)
async def acknowledge_incident(
    incident_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    incident = await _get_incident_or_404(incident_id, org, db)
    if incident.status != "open":
        raise HTTPException(status_code=409, detail=f"Incident is already {incident.status}")
    incident.status = "acknowledged"
    incident.acknowledged_at = datetime.now(timezone.utc)
    if hasattr(incident, "acknowledged_by_id"):
        incident.acknowledged_by_id = user.id
    await db.commit()
    return await _incident_response(incident, db)


@router.patch("/{incident_id}/resolve", response_model=IncidentResponse)
async def resolve_incident(
    incident_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    incident = await _get_incident_or_404(incident_id, org, db)
    if incident.status == "resolved":
        raise HTTPException(status_code=409, detail="Incident already resolved")
    incident.status = "resolved"
    incident.resolved_at = datetime.now(timezone.utc)
    if hasattr(incident, "resolved_by_id"):
        incident.resolved_by_id = user.id
    await db.commit()
    return await _incident_response(incident, db)


@router.patch("/{incident_id}/assign", response_model=IncidentResponse)
async def assign_incident(
    incident_id: str,
    body: AssignIncidentBody,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    incident = await _get_incident_or_404(incident_id, org, db)

    # Validate assignee belongs to org
    if body.assignee_id is not None:
        target_user = await db.scalar(
            select(User).where(User.id == body.assignee_id, User.org_id == org.id)
        )
        if not target_user:
            raise HTTPException(status_code=404, detail="Assignee user not found in this org")
        incident.assignee_id = target_user.id
    elif body.assignee_id is None and "assignee_id" in body.model_fields_set:
        incident.assignee_id = None

    # Validate team belongs to org
    if body.assigned_team_id is not None:
        target_team = await db.scalar(
            select(Team).where(Team.id == body.assigned_team_id, Team.org_id == org.id)
        )
        if not target_team:
            raise HTTPException(status_code=404, detail="Team not found in this org")
        incident.assigned_team_id = target_team.id
    elif body.assigned_team_id is None and "assigned_team_id" in body.model_fields_set:
        incident.assigned_team_id = None

    await db.commit()

    # Fire notification task (non-blocking, best-effort)
    try:
        from app.tasks import notify_incident_assignment
        notify_incident_assignment.delay(incident_id)
    except Exception:
        pass

    return await _incident_response(incident, db)
