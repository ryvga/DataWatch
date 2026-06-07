from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.oncall import OncallSchedule
from app.models.organization import Organization
from app.models.team import Team, TeamMember
from app.models.user import User
from app.routers.auth import get_current_user_from_jwt

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    name: str
    description: str | None = None
    color: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None


class TeamResponse(BaseModel):
    id: str
    name: str
    description: str | None
    color: str | None
    member_count: int
    current_oncall: str | None  # user full_name or email, or None
    created_at: datetime


class TeamMemberAdd(BaseModel):
    user_id: str
    role: str = "member"


class TeamMemberRoleUpdate(BaseModel):
    role: str


class TeamMemberResponse(BaseModel):
    user_id: str
    email: str
    full_name: str | None
    team_role: str
    joined_at: datetime


class OncallSlotCreate(BaseModel):
    user_id: str
    starts_at: datetime
    ends_at: datetime


class OncallSlotResponse(BaseModel):
    id: str
    user_id: str
    user_name: str
    user_email: str
    starts_at: datetime
    ends_at: datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(user: User) -> None:
    role = getattr(user, "role", None)
    is_admin = getattr(user, "is_admin", False)
    if role is not None:
        # newer schema: role field
        if role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="Admin or owner required")
    else:
        # older schema: is_admin boolean
        if not is_admin:
            raise HTTPException(status_code=403, detail="Admin required")


async def _get_team_or_404(team_id: str, org: Organization, db: AsyncSession) -> Team:
    team = await db.scalar(
        select(Team).where(Team.id == team_id, Team.org_id == org.id)
    )
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


async def _current_oncall_name(team_id, db: AsyncSession) -> str | None:
    """Return the full_name or email of whoever is currently on-call, or None."""
    now = datetime.now(timezone.utc)
    slot = await db.scalar(
        select(OncallSchedule).where(
            OncallSchedule.team_id == team_id,
            OncallSchedule.starts_at <= now,
            OncallSchedule.ends_at >= now,
        ).limit(1)
    )
    if not slot:
        return None
    user = await db.get(User, slot.user_id)
    if not user:
        return None
    return getattr(user, "full_name", None) or user.email


async def _member_count(team_id, db: AsyncSession) -> int:
    from sqlalchemy import func
    result = await db.scalar(
        select(func.count()).where(TeamMember.team_id == team_id)
    )
    return result or 0


def _team_response(team: Team, member_count: int, current_oncall: str | None) -> TeamResponse:
    return TeamResponse(
        id=str(team.id),
        name=team.name,
        description=team.description,
        color=team.color,
        member_count=member_count,
        current_oncall=current_oncall,
        created_at=team.created_at,
    )


# ── Endpoints: Teams ──────────────────────────────────────────────────────────

@router.get("", response_model=list[TeamResponse])
async def list_teams(
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    teams = (await db.scalars(
        select(Team).where(Team.org_id == org.id).order_by(Team.created_at)
    )).all()
    result = []
    for team in teams:
        mc = await _member_count(team.id, db)
        oc = await _current_oncall_name(team.id, db)
        result.append(_team_response(team, mc, oc))
    return result


@router.post("", response_model=TeamResponse, status_code=201)
async def create_team(
    body: TeamCreate,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_admin(user)
    team = Team(
        org_id=org.id,
        name=body.name,
        description=body.description,
        color=body.color,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return _team_response(team, 0, None)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    team = await _get_team_or_404(team_id, org, db)
    mc = await _member_count(team.id, db)
    oc = await _current_oncall_name(team.id, db)
    return _team_response(team, mc, oc)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    body: TeamUpdate,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_admin(user)
    team = await _get_team_or_404(team_id, org, db)
    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(team, field, value)
    await db.commit()
    await db.refresh(team)
    mc = await _member_count(team.id, db)
    oc = await _current_oncall_name(team.id, db)
    return _team_response(team, mc, oc)


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_admin(user)
    team = await _get_team_or_404(team_id, org, db)
    await db.delete(team)
    await db.commit()


# ── Endpoints: Members ────────────────────────────────────────────────────────

@router.get("/{team_id}/members", response_model=list[TeamMemberResponse])
async def list_team_members(
    team_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    team = await _get_team_or_404(team_id, org, db)
    members = (await db.scalars(
        select(TeamMember).where(TeamMember.team_id == team.id)
    )).all()
    result = []
    for m in members:
        u = await db.get(User, m.user_id)
        if not u:
            continue
        result.append(TeamMemberResponse(
            user_id=str(m.user_id),
            email=u.email,
            full_name=getattr(u, "full_name", None),
            team_role=m.role,
            joined_at=m.joined_at,
        ))
    return result


@router.post("/{team_id}/members", response_model=TeamMemberResponse, status_code=201)
async def add_team_member(
    team_id: str,
    body: TeamMemberAdd,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_admin(user)
    team = await _get_team_or_404(team_id, org, db)

    # Validate user belongs to same org
    target_user = await db.scalar(
        select(User).where(User.id == body.user_id, User.org_id == org.id)
    )
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found in this org")

    # Check not already a member
    existing = await db.scalar(
        select(TeamMember).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == target_user.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member of this team")

    member = TeamMember(team_id=team.id, user_id=target_user.id, role=body.role)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return TeamMemberResponse(
        user_id=str(member.user_id),
        email=target_user.email,
        full_name=getattr(target_user, "full_name", None),
        team_role=member.role,
        joined_at=member.joined_at,
    )


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_team_member(
    team_id: str,
    user_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_admin(user)
    team = await _get_team_or_404(team_id, org, db)
    member = await db.scalar(
        select(TeamMember).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user_id,
        )
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    await db.delete(member)
    await db.commit()


@router.patch("/{team_id}/members/{user_id}", response_model=TeamMemberResponse)
async def update_team_member_role(
    team_id: str,
    user_id: str,
    body: TeamMemberRoleUpdate,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_admin(user)
    if body.role not in ("lead", "member"):
        raise HTTPException(status_code=422, detail="Role must be 'lead' or 'member'")
    team = await _get_team_or_404(team_id, org, db)
    member = await db.scalar(
        select(TeamMember).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user_id,
        )
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = body.role
    await db.commit()
    await db.refresh(member)
    target_user = await db.get(User, member.user_id)
    return TeamMemberResponse(
        user_id=str(member.user_id),
        email=target_user.email if target_user else "",
        full_name=getattr(target_user, "full_name", None) if target_user else None,
        team_role=member.role,
        joined_at=member.joined_at,
    )


# ── Endpoints: On-call ────────────────────────────────────────────────────────

@router.get("/{team_id}/oncall", response_model=list[OncallSlotResponse])
async def list_oncall(
    team_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    team = await _get_team_or_404(team_id, org, db)
    slots = (await db.scalars(
        select(OncallSchedule)
        .where(OncallSchedule.team_id == team.id)
        .order_by(OncallSchedule.starts_at)
    )).all()
    result = []
    for slot in slots:
        u = await db.get(User, slot.user_id)
        result.append(OncallSlotResponse(
            id=str(slot.id),
            user_id=str(slot.user_id),
            user_name=getattr(u, "full_name", None) or (u.email if u else ""),
            user_email=u.email if u else "",
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
        ))
    return result


@router.post("/{team_id}/oncall", response_model=OncallSlotResponse, status_code=201)
async def create_oncall_slot(
    team_id: str,
    body: OncallSlotCreate,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_admin(user)
    team = await _get_team_or_404(team_id, org, db)

    # Validate user is in this org
    target_user = await db.scalar(
        select(User).where(User.id == body.user_id, User.org_id == org.id)
    )
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found in this org")

    slot = OncallSchedule(
        team_id=team.id,
        user_id=target_user.id,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
    )
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    return OncallSlotResponse(
        id=str(slot.id),
        user_id=str(slot.user_id),
        user_name=getattr(target_user, "full_name", None) or target_user.email,
        user_email=target_user.email,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
    )


@router.delete("/{team_id}/oncall/{slot_id}", status_code=204)
async def delete_oncall_slot(
    team_id: str,
    slot_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_admin(user)
    team = await _get_team_or_404(team_id, org, db)
    slot = await db.scalar(
        select(OncallSchedule).where(
            OncallSchedule.id == slot_id,
            OncallSchedule.team_id == team.id,
        )
    )
    if not slot:
        raise HTTPException(status_code=404, detail="On-call slot not found")
    await db.delete(slot)
    await db.commit()


@router.get("/{team_id}/oncall/current")
async def get_current_oncall(
    team_id: str,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    team = await _get_team_or_404(team_id, org, db)
    now = datetime.now(timezone.utc)
    slot = await db.scalar(
        select(OncallSchedule).where(
            OncallSchedule.team_id == team.id,
            OncallSchedule.starts_at <= now,
            OncallSchedule.ends_at >= now,
        ).limit(1)
    )
    if not slot:
        return {"current_oncall": None}
    u = await db.get(User, slot.user_id)
    return {
        "current_oncall": {
            "slot_id": str(slot.id),
            "user_id": str(slot.user_id),
            "user_name": getattr(u, "full_name", None) or (u.email if u else ""),
            "user_email": u.email if u else "",
            "starts_at": slot.starts_at,
            "ends_at": slot.ends_at,
        }
    }
