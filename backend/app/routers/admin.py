"""Staff-only admin portal endpoints."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import generate_api_key, generate_invite_token, hash_password
from app.database import get_db
from app.models.data_source import DataSource
from app.models.incident import Incident
from app.models.invite import Invite
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.models.user import ApiKey, StaffUser, User
from app.routers.auth import get_current_staff
from app.services.crypto import CryptoService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrgSummary(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    subscription_status: str
    user_count: int
    created_at: str
    has_llm_key: bool
    llm_model: str | None
    sources_count: int = 0
    tables_count: int = 0
    members_count: int = 0


class OrgDetail(OrgSummary):
    stripe_customer_id: str | None
    trial_ends_at: str | None


class UpdatePlanRequest(BaseModel):
    plan: str
    subscription_status: str | None = None


class SetLLMKeyRequest(BaseModel):
    api_key: str
    model: str | None = None


class CreateStaffRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class StaffSummary(BaseModel):
    id: str
    email: str
    full_name: str | None
    is_active: bool
    created_at: str


class UserSummary(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    org_slug: str
    created_at: str
    last_login_at: str | None
    is_active: bool = True


class SetApiKeyRequest(BaseModel):
    name: str = "default"


class CancelSubscriptionRequest(BaseModel):
    reason: str = "Staff initiated cancellation"


class ChangeRoleRequest(BaseModel):
    role: str


# ── Organizations ─────────────────────────────────────────────────────────────

@router.get("/orgs")
async def list_orgs(
    search: str | None = Query(None),
    plan: str | None = Query(None),
    subscription_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    query = select(Organization).order_by(Organization.created_at.desc())
    if search:
        query = query.where(
            Organization.name.ilike(f"%{search}%") | Organization.slug.ilike(f"%{search}%")
        )
    if plan:
        query = query.where(Organization.plan == plan)
    if subscription_status:
        query = query.where(Organization.subscription_status == subscription_status)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    orgs = (await db.scalars(query.offset((page - 1) * per_page).limit(per_page))).all()

    result = []
    for org in orgs:
        user_count = await db.scalar(select(func.count()).where(User.org_id == org.id))
        sources_count = await db.scalar(select(func.count()).where(DataSource.org_id == org.id))
        tables_count = await db.scalar(
            select(func.count()).where(
                MonitoredTable.source_id.in_(
                    select(DataSource.id).where(DataSource.org_id == org.id)
                )
            )
        )
        result.append(OrgSummary(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            plan=org.plan,
            subscription_status=org.subscription_status,
            user_count=user_count or 0,
            created_at=org.created_at.isoformat(),
            has_llm_key=bool(org.llm_api_key_encrypted),
            llm_model=org.llm_model,
            sources_count=sources_count or 0,
            tables_count=tables_count or 0,
            members_count=user_count or 0,
        ))
    return {"items": result, "total": total or 0}


@router.get("/orgs/{org_id}", response_model=OrgDetail)
async def get_org(
    org_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    count = await db.scalar(select(func.count()).where(User.org_id == org.id))
    sources_count = await db.scalar(select(func.count()).where(DataSource.org_id == org.id))
    tables_count = await db.scalar(
        select(func.count()).where(
            MonitoredTable.source_id.in_(
                select(DataSource.id).where(DataSource.org_id == org.id)
            )
        )
    )
    return OrgDetail(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        subscription_status=org.subscription_status,
        user_count=count or 0,
        created_at=org.created_at.isoformat(),
        has_llm_key=bool(org.llm_api_key_encrypted),
        llm_model=org.llm_model,
        stripe_customer_id=org.stripe_customer_id,
        trial_ends_at=org.trial_ends_at.isoformat() if org.trial_ends_at else None,
        sources_count=sources_count or 0,
        tables_count=tables_count or 0,
        members_count=count or 0,
    )


@router.patch("/orgs/{org_id}/plan")
async def update_plan(
    org_id: str,
    body: UpdatePlanRequest,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org.plan = body.plan
    if body.subscription_status:
        org.subscription_status = body.subscription_status
    await db.commit()
    return {"ok": True}


@router.put("/orgs/{org_id}/llm-key")
async def set_llm_key(
    org_id: str,
    body: SetLLMKeyRequest,
    staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    crypto = CryptoService()
    org.llm_api_key_encrypted = crypto.encrypt_for_org(body.api_key, str(org.id))
    if body.model:
        org.llm_model = body.model
    await db.commit()
    return {"ok": True}


@router.delete("/orgs/{org_id}/llm-key")
async def remove_llm_key(
    org_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org.llm_api_key_encrypted = None
    org.llm_model = None
    await db.commit()
    return {"ok": True}


@router.post("/orgs/{org_id}/api-key", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    org_id: str,
    body: SetApiKeyRequest,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    raw, hashed = generate_api_key()
    key = ApiKey(org_id=org.id, name=body.name, key_hash=hashed)
    db.add(key)
    await db.commit()
    return {"api_key": raw, "name": body.name, "id": str(key.id)}


@router.patch("/orgs/{org_id}/suspend")
async def suspend_org(
    org_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org.subscription_status = "suspended"
    await db.commit()
    return {"ok": True}


@router.patch("/orgs/{org_id}/unsuspend")
async def unsuspend_org(
    org_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org.subscription_status = "active"
    await db.commit()
    return {"ok": True}


@router.delete("/orgs/{org_id}")
async def delete_org(
    org_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org.subscription_status = "suspended"
    await db.commit()
    return {"ok": True}


@router.get("/orgs/{org_id}/usage")
async def get_org_usage(
    org_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    sources_count = await db.scalar(select(func.count()).where(DataSource.org_id == org.id))
    tables_count = await db.scalar(
        select(func.count()).where(
            MonitoredTable.source_id.in_(
                select(DataSource.id).where(DataSource.org_id == org.id)
            )
        )
    )
    incidents_count = await db.scalar(select(func.count()).where(Incident.org_id == org.id))
    open_incidents = await db.scalar(
        select(func.count()).where(Incident.org_id == org.id, Incident.status == "open")
    )
    members_count = await db.scalar(select(func.count()).where(User.org_id == org.id))
    week_ago = datetime.now(UTC) - timedelta(days=7)
    incidents_7d = await db.scalar(
        select(func.count()).where(Incident.org_id == org.id, Incident.created_at >= week_ago)
    )
    return {
        "sources_count": sources_count or 0,
        "tables_count": tables_count or 0,
        "incidents_count": incidents_count or 0,
        "open_incidents": open_incidents or 0,
        "members_count": members_count or 0,
        "incidents_last_7d": incidents_7d or 0,
    }


@router.get("/orgs/{org_id}/sources")
async def get_org_sources(
    org_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    sources = (await db.scalars(select(DataSource).where(DataSource.org_id == org_id))).all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "type": s.type,
            "status": s.status,
            "created_at": s.created_at.isoformat(),
        }
        for s in sources
    ]


@router.post("/orgs/{org_id}/subscription/cancel")
async def cancel_org_subscription(
    org_id: str,
    body: CancelSubscriptionRequest = None,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    org.subscription_status = "cancelled"
    await db.commit()
    return {"ok": True}


@router.patch("/orgs/{org_id}/users/{user_id}/deactivate")
async def deactivate_org_user(
    org_id: str,
    user_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(User).where(User.id == user_id, User.org_id == org_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found in this org")
    user.is_active = False
    await db.commit()
    return {"ok": True}


@router.patch("/orgs/{org_id}/users/{user_id}/reactivate")
async def reactivate_org_user(
    org_id: str,
    user_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(User).where(User.id == user_id, User.org_id == org_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found in this org")
    user.is_active = True
    await db.commit()
    return {"ok": True}


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserSummary])
async def list_all_users(
    search: str | None = Query(None),
    org: str | None = Query(None),
    role: str | None = Query(None),
    active: bool | None = Query(None),
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.created_at.desc())
    if search:
        query = query.where(
            User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%")
        )
    if org:
        # Try to match by slug first, then by id
        org_obj = await db.scalar(
            select(Organization).where(Organization.slug == org)
        )
        if not org_obj:
            org_obj = await db.get(Organization, org)
        if org_obj:
            query = query.where(User.org_id == org_obj.id)
    if role:
        query = query.where(User.role == role)
    if active is not None:
        query = query.where(User.is_active == active)

    users = (await db.scalars(query)).all()
    result = []
    for u in users:
        org_obj = await db.get(Organization, u.org_id)
        result.append(UserSummary(
            id=str(u.id),
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            org_slug=org_obj.slug if org_obj else "",
            created_at=u.created_at.isoformat(),
            last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
            is_active=u.is_active,
        ))
    return result


@router.get("/orgs/{org_id}/users", response_model=list[UserSummary])
async def list_org_users(
    org_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    org = await db.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    users = (await db.scalars(select(User).where(User.org_id == org.id))).all()
    return [
        UserSummary(
            id=str(u.id),
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            org_slug=org.slug,
            created_at=u.created_at.isoformat(),
            last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
            is_active=u.is_active,
        )
        for u in users
    ]


@router.patch("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    await db.commit()
    return {"ok": True}


@router.patch("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    await db.commit()
    return {"ok": True}


@router.patch("/users/{user_id}/role")
async def change_user_role(
    user_id: str,
    body: ChangeRoleRequest,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    valid_roles = {"owner", "admin", "member", "viewer"}
    if body.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")
    user.role = body.role
    await db.commit()
    return {"ok": True}


# ── Staff Management ──────────────────────────────────────────────────────────

@router.get("/staff", response_model=list[StaffSummary])
async def list_staff(
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    staff_list = (await db.scalars(select(StaffUser).order_by(StaffUser.created_at))).all()
    return [
        StaffSummary(
            id=str(s.id),
            email=s.email,
            full_name=s.full_name,
            is_active=s.is_active,
            created_at=s.created_at.isoformat(),
        )
        for s in staff_list
    ]


@router.post("/staff", response_model=StaffSummary, status_code=status.HTTP_201_CREATED)
async def create_staff(
    body: CreateStaffRequest,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(select(StaffUser).where(StaffUser.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    new_staff = StaffUser(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(new_staff)
    await db.commit()
    return StaffSummary(
        id=str(new_staff.id),
        email=new_staff.email,
        full_name=new_staff.full_name,
        is_active=new_staff.is_active,
        created_at=new_staff.created_at.isoformat(),
    )


@router.patch("/staff/{staff_id}/deactivate")
async def deactivate_staff(
    staff_id: str,
    current_staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    if str(current_staff.id) == staff_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    target = await db.get(StaffUser, staff_id)
    if not target:
        raise HTTPException(status_code=404, detail="Staff not found")
    target.is_active = False
    await db.commit()
    return {"ok": True}


@router.post("/staff/{staff_id}/reset-password")
async def reset_staff_password(
    staff_id: str,
    current_staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    import secrets
    target = await db.get(StaffUser, staff_id)
    if not target:
        raise HTTPException(status_code=404, detail="Staff not found")
    new_password = secrets.token_urlsafe(12)
    target.password_hash = hash_password(new_password)
    await db.commit()
    return {"new_password": new_password}


# ── Invites ───────────────────────────────────────────────────────────────────

@router.get("/orgs/{org_id}/invites")
async def list_invites(
    org_id: str,
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    invites = (await db.scalars(select(Invite).where(Invite.org_id == org_id))).all()
    return [
        {
            "id": str(i.id),
            "email": i.email,
            "role": i.role,
            "expires_at": i.expires_at.isoformat(),
            "accepted_at": i.accepted_at.isoformat() if i.accepted_at else None,
            "created_at": i.created_at.isoformat(),
        }
        for i in invites
    ]


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    from app.services.plans import PLAN_LIMITS
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    thirty_ago = now - timedelta(days=30)

    total_orgs = await db.scalar(select(func.count(Organization.id)))
    total_users = await db.scalar(select(func.count(User.id)))
    total_sources = await db.scalar(select(func.count(DataSource.id)))
    total_tables = await db.scalar(select(func.count(MonitoredTable.id)))
    new_orgs_7d = await db.scalar(
        select(func.count(Organization.id)).where(Organization.created_at >= week_ago)
    )
    new_orgs_30d = await db.scalar(
        select(func.count(Organization.id)).where(Organization.created_at >= thirty_ago)
    )
    active_users_7d = await db.scalar(
        select(func.count(User.id)).where(User.last_login_at >= week_ago)
    )
    incidents_7d = await db.scalar(
        select(func.count(Incident.id)).where(Incident.created_at >= week_ago)
    )
    active_subs = await db.scalar(
        select(func.count(Organization.id)).where(
            Organization.subscription_status.in_(["active", "trialing"])
        )
    )

    plan_prices = {"free": 0, "starter": 49, "growth": 149, "agency": 299, "enterprise": 299}
    active_orgs = (
        await db.scalars(
            select(Organization).where(
                Organization.subscription_status.in_(["active", "trialing"])
            )
        )
    ).all()
    mrr = sum(plan_prices.get(org.plan, 0) for org in active_orgs)

    return {
        "total_orgs": total_orgs or 0,
        "total_users": total_users or 0,
        "total_sources": total_sources or 0,
        "total_tables": total_tables or 0,
        "new_orgs_last_7d": new_orgs_7d or 0,
        "new_orgs_last_30d": new_orgs_30d or 0,
        "active_users_last_7d": active_users_7d or 0,
        "incidents_last_7d": incidents_7d or 0,
        "active_subscriptions_count": active_subs or 0,
        "mrr": mrr,
    }
