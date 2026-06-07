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
    duration_minutes: int | None
    # Assignment fields
    assignee_id: str | None = None
    assigned_team_id: str | None = None
    assignee_name: str | None = None
    assigned_team_name: str | None = None
    acknowledged_by_id: str | None = None
    resolved_by_id: str | None = None


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


def _duration_minutes(i: Incident) -> int | None:
    from datetime import timezone, timedelta
    if not i.created_at:
        return None
    end = i.resolved_at or datetime.now(timezone.utc)
    start = i.created_at if i.created_at.tzinfo else i.created_at.replace(tzinfo=timezone.utc)
    if not end.tzinfo:
        end = end.replace(tzinfo=timezone.utc)
    delta = end - start
    return max(0, int(delta.total_seconds() / 60))


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
        resolved_at=i.resolved_at,
        duration_minutes=_duration_minutes(i),
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
    statuses: str | None = None,
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

    # Support ?statuses=open,acknowledged,investigating (comma-separated multi-status)
    if statuses:
        status_list = [s.strip() for s in statuses.split(",") if s.strip()]
        if status_list:
            q = q.where(Incident.status.in_(status_list))
    elif status:
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


@router.get("/stats")
async def get_incident_stats(
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Quick stats for dashboard — open/ack/investigating/resolved counts."""
    from sqlalchemy import func
    from datetime import timezone, timedelta
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
    if incident.status in ("resolved", "acknowledged", "investigating"):
        raise HTTPException(status_code=409, detail=f"Incident is already {incident.status}")
    old_status = incident.status
    incident.status = "acknowledged"
    incident.acknowledged_at = datetime.now(timezone.utc)
    if hasattr(incident, "acknowledged_by_id"):
        incident.acknowledged_by_id = user.id
    await db.commit()
    try:
        from app.tasks import notify_incident_status_change
        notify_incident_status_change.delay(incident_id, "open", "acknowledged")
    except Exception:
        pass
    return await _incident_response(incident, db)


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
    old_status = incident.status
    incident.status = "resolved"
    incident.resolved_at = datetime.now(timezone.utc)
    if hasattr(incident, "resolved_by_id"):
        incident.resolved_by_id = user.id
    await db.commit()
    try:
        from app.tasks import notify_incident_status_change
        notify_incident_status_change.delay(incident_id, "open", "resolved")
    except Exception:
        pass
    return await _incident_response(incident, db)


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
    narration = dict(incident.llm_narration or {})
    muted_until = (datetime.now(timezone.utc) + timedelta(hours=body.hours)).isoformat()
    narration["muted_until"] = muted_until
    narration["muted_hours"] = body.hours
    incident.llm_narration = narration
    await db.commit()
    return await _incident_response(incident, db)


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
    narration = dict(incident.llm_narration or {})
    from datetime import timezone, timedelta
    narration["false_positive_until"] = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    narration["false_positive_reason"] = "Marked false positive by user"
    incident.llm_narration = narration
    if not incident.title.startswith("[FP]"):
        incident.title = f"[FP] {incident.title}"
    await db.commit()
    return await _incident_response(incident, db)


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

    incident.llm_narration = None
    flag_modified(incident, "llm_narration")
    await db.commit()
    await db.refresh(incident)

    invalidate_narration_cache(incident_id)
    generate_llm_narration.delay(incident_id)

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

    if body.assignee_id is not None:
        target_user = await db.scalar(
            select(User).where(User.id == body.assignee_id, User.org_id == org.id)
        )
        if not target_user:
            raise HTTPException(status_code=404, detail="Assignee user not found in this org")
        incident.assignee_id = target_user.id
    elif body.assignee_id is None and "assignee_id" in body.model_fields_set:
        incident.assignee_id = None

    if body.assigned_team_id is not None:
        from app.models.team import Team
        target_team = await db.scalar(
            select(Team).where(Team.id == body.assigned_team_id, Team.org_id == org.id)
        )
        if not target_team:
            raise HTTPException(status_code=404, detail="Team not found in this org")
        incident.assigned_team_id = target_team.id
    elif body.assigned_team_id is None and "assigned_team_id" in body.model_fields_set:
        incident.assigned_team_id = None

    await db.commit()

    try:
        from app.tasks import notify_incident_assignment
        notify_incident_assignment.delay(incident_id)
    except Exception:
        pass

    return await _incident_response(incident, db)
