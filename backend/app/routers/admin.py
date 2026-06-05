"""Staff-only admin portal endpoints."""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import generate_api_key, generate_invite_token, hash_password
from app.database import get_db
from app.models.invite import Invite
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


class SetApiKeyRequest(BaseModel):
    name: str = "default"


# ── Organizations ─────────────────────────────────────────────────────────────

@router.get("/orgs", response_model=list[OrgSummary])
async def list_orgs(
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    orgs = (await db.scalars(select(Organization).order_by(Organization.created_at.desc()))).all()
    result = []
    for org in orgs:
        count = await db.scalar(select(func.count()).where(User.org_id == org.id))
        result.append(OrgSummary(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            plan=org.plan,
            subscription_status=org.subscription_status,
            user_count=count or 0,
            created_at=org.created_at.isoformat(),
            has_llm_key=bool(org.llm_api_key_encrypted),
            llm_model=org.llm_model,
        ))
    return result


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


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserSummary])
async def list_all_users(
    _staff: StaffUser = Depends(get_current_staff),
    db: AsyncSession = Depends(get_db),
):
    users = (await db.scalars(select(User).order_by(User.created_at.desc()))).all()
    result = []
    for u in users:
        org = await db.get(Organization, u.org_id)
        result.append(UserSummary(
            id=str(u.id),
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            org_slug=org.slug if org else "",
            created_at=u.created_at.isoformat(),
            last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
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
        )
        for u in users
    ]


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
