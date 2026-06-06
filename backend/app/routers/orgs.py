from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.check_result import CheckResult
from app.models.incident import Incident
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.models.data_source import DataSource
from app.models.user import User
from app.routers.auth import get_current_org_from_jwt
from app.services.health_score import compute_health_score, HealthBreakdown

router = APIRouter(prefix="/orgs", tags=["orgs"])


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    subscription_status: str


class OrgMemberResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    created_at: datetime
    last_login_at: datetime | None
    is_active: bool


class OrgHealthResponse(BaseModel):
    score: float
    grade: str
    color: str
    total_checks: int
    passed_checks: int
    failed_checks: int
    open_incidents: int
    monitored_tables: int
    sources: int
    window_hours: int


@router.get("/me", response_model=OrgResponse)
async def get_my_org(org: Organization = Depends(get_current_org_from_jwt)):
    return OrgResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        subscription_status=org.subscription_status,
    )


@router.get("/me/members", response_model=list[OrgMemberResponse])
async def get_org_members(
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Return all users in the current org."""
    users = (await db.scalars(
        select(User).where(User.org_id == org.id).order_by(User.created_at)
    )).all()
    return [
        OrgMemberResponse(
            id=str(u.id),
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
            is_active=u.is_active,
        )
        for u in users
    ]


@router.get("/me/health", response_model=OrgHealthResponse)
async def get_org_health(
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Compute the org-wide health score from the last 24h of check results."""
    window = datetime.now(UTC) - timedelta(hours=24)

    # All check results in window for this org's tables
    checks = (await db.scalars(
        select(CheckResult)
        .join(MonitoredTable, CheckResult.table_id == MonitoredTable.id)
        .join(DataSource, MonitoredTable.source_id == DataSource.id)
        .where(DataSource.org_id == org.id, CheckResult.checked_at >= window)
    )).all()

    open_incidents = await db.scalar(
        select(__import__("sqlalchemy", fromlist=["func"]).func.count())
        .where(Incident.org_id == org.id, Incident.status == "open")
    ) or 0

    sources_count = await db.scalar(
        select(__import__("sqlalchemy", fromlist=["func"]).func.count())
        .where(DataSource.org_id == org.id, DataSource.status != "paused")
    ) or 0

    tables_count = await db.scalar(
        select(__import__("sqlalchemy", fromlist=["func"]).func.count())
        .select_from(MonitoredTable)
        .join(DataSource, MonitoredTable.source_id == DataSource.id)
        .where(DataSource.org_id == org.id, MonitoredTable.is_active == True)
    ) or 0

    # Map check_results to simple dicts for health score
    check_dicts = []
    for cr in checks:
        # Map severity from incident severity — use check_name heuristics
        sev = "P3"
        if "row_count_zero" in cr.check_name or "freshness_sla" in cr.check_name:
            sev = "P1"
        elif "schema_drift" in cr.check_name or "isolation_forest" in cr.check_name:
            sev = "P2"
        check_dicts.append({"status": cr.status, "severity": sev})

    breakdown = compute_health_score(check_dicts, open_incidents=open_incidents)

    return OrgHealthResponse(
        score=breakdown.score,
        grade=breakdown.grade,
        color=breakdown.color,
        total_checks=breakdown.total_checks,
        passed_checks=breakdown.passed_checks,
        failed_checks=breakdown.failed_checks,
        open_incidents=open_incidents,
        monitored_tables=tables_count,
        sources=sources_count,
        window_hours=24,
    )
