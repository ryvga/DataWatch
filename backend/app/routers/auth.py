import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)
from app.database import get_db
from app.models.organization import Organization
from app.models.user import ApiKey, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    org_name: str
    org_slug: str
    email: EmailStr
    password: str


class RegisterResponse(BaseModel):
    org_id: str
    api_key: str  # shown once


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check slug uniqueness
    existing = await db.scalar(select(Organization).where(Organization.slug == body.org_slug))
    if existing:
        raise HTTPException(status_code=409, detail="Slug already taken")

    org = Organization(name=body.org_name, slug=body.org_slug, plan="free")
    db.add(org)
    await db.flush()

    user = User(org_id=org.id, email=body.email, password_hash=hash_password(body.password))
    db.add(user)

    raw_key, key_hash = generate_api_key()
    api_key = ApiKey(org_id=org.id, key_hash=key_hash, name="default")
    db.add(api_key)

    return RegisterResponse(org_id=str(org.id), api_key=raw_key)


class InviteAcceptRequest(BaseModel):
    token: str
    full_name: str
    password: str


@router.post("/invites/{token}/accept", response_model=TokenResponse)
async def accept_invite(
    token: str,
    body: InviteAcceptRequest,
    db: AsyncSession = Depends(get_db),
):
    """Accept an org invite and create user account. Notifies org admins of new member."""
    # Import Invite model dynamically — added by migration agent
    try:
        from app.models.invite import Invite
    except ImportError:
        raise HTTPException(status_code=501, detail="Invite feature not yet available")

    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    invite = await db.scalar(select(Invite).where(Invite.token == token))
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    if not invite or invite.accepted_at is not None or invite.expires_at <= now:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")

    org = await db.get(Organization, invite.org_id)
    if not org:
        raise HTTPException(status_code=400, detail="Invite workspace no longer exists")

    existing = await db.scalar(
        select(User).where(User.org_id == invite.org_id, User.email == invite.email)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Email is already a member of this workspace")

    user = User(
        org_id=invite.org_id,
        email=invite.email,
        password_hash=hash_password(body.password),
        role=getattr(invite, "role", "member"),
        full_name=body.full_name,
    )
    db.add(user)
    invite.accepted_at = now
    await db.commit()
    await db.refresh(user)

    # Notify org admins that a new member joined
    try:
        from app.services.email import send_member_joined_email
        admin_users = (await db.scalars(
            select(User).where(
                User.org_id == org.id,
                User.role.in_(["owner", "admin"]),
                User.id != user.id,
            )
        )).all()
        admin_emails = [u.email for u in admin_users]
        if admin_emails:
            send_member_joined_email(
                admin_emails, org.name,
                user.full_name or user.email, user.email, user.role
            )
    except Exception as e:
        logger.warning("Failed to send member-joined email: %s", e)

    jwt_token = create_access_token(sub=str(user.id), org_id=str(user.org_id))
    return TokenResponse(access_token=jwt_token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(sub=str(user.id), org_id=str(user.org_id))
    return TokenResponse(access_token=token)


# ── Dependencies ──────────────────────────────────────────────────────────────

async def get_current_org_from_api_key(
    x_api_key: str = Header(..., alias="x-api-key"),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Dependency: validates x-api-key header, returns org."""
    keys = (await db.scalars(select(ApiKey))).all()
    for key in keys:
        if verify_api_key(x_api_key, key.key_hash):
            org = await db.get(Organization, key.org_id)
            if org:
                return org
    raise HTTPException(status_code=401, detail="Invalid API key")


async def get_current_org_from_jwt(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Dependency: validates Bearer JWT, returns org."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:]
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    org = await db.get(Organization, payload["org_id"])
    if not org:
        raise HTTPException(status_code=401, detail="Org not found")
    return org
