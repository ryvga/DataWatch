import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from collections import defaultdict
import time
import threading
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from jose import JWTError
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    create_access_token,
    create_staff_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.invite import Invite
from app.models.organization import Organization
from app.models.user import ApiKey, StaffUser, User
from app.services import email as email_service
from app.services.plans import enforce_member_limit

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Simple in-process rate limiter for login endpoints ────────────────────────
# Uses sliding window: max 10 attempts per IP per 60 seconds.
# Production should use Redis-backed rate limiting.
_RATE_LIMIT_WINDOW = 60   # seconds
_RATE_LIMIT_MAX = 10      # attempts per window
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()
_password_reset_tokens: dict[str, dict] = {}
_password_reset_lock = asyncio.Lock()

def _check_rate_limit(ip: str) -> None:
    now = time.time()
    with _rate_lock:
        timestamps = _rate_store[ip]
        # Purge old
        _rate_store[ip] = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
        if len(_rate_store[ip]) >= _RATE_LIMIT_MAX:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Please wait before trying again.",
                headers={"Retry-After": str(_RATE_LIMIT_WINDOW)},
            )
        _rate_store[ip].append(now)


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    org_name: str
    org_slug: str
    email: EmailStr
    password: str
    full_name: str | None = None


class RegisterResponse(BaseModel):
    org_id: str
    org_slug: str
    message: str = "Workspace created. Sign in to continue."


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    org_slug: str  # required — workspace identifier


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    org_slug: str
    org_name: str
    user_role: str


class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str


class StaffTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    staff_id: str
    email: str


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "viewer"]


class InviteResponse(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime


class InviteAcceptRequest(BaseModel):
    full_name: str
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr
    org_slug: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None


class ProfileResponse(BaseModel):
    id: str
    org_id: str
    email: str
    full_name: str | None
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(Organization).where(Organization.slug == body.org_slug))
    if existing:
        raise HTTPException(status_code=409, detail="Workspace slug already taken")

    email_taken = await db.scalar(select(User).where(User.email == body.email))
    if email_taken:
        raise HTTPException(status_code=409, detail="Email already registered")

    org = Organization(name=body.org_name, slug=body.org_slug, plan="free")
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email=body.email,
        password_hash=hash_password(body.password),
        role="owner",
        full_name=body.full_name,
    )
    db.add(user)
    await db.commit()

    return RegisterResponse(org_id=str(org.id), org_slug=org.slug)


# ── Login ─────────────────────────────────────────────────────────────────────

_INVALID = HTTPException(status_code=401, detail="Invalid email or password")

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    _check_rate_limit(request.client.host if request.client else "unknown")
    # Never reveal whether workspace or user exists — always same error
    org = await db.scalar(select(Organization).where(Organization.slug == body.org_slug))
    if not org:
        raise _INVALID

    user = await db.scalar(
        select(User).where(User.email == body.email, User.org_id == org.id)
    )
    if not user or not verify_password(body.password, user.password_hash):
        raise _INVALID

    # Update last login
    await db.execute(
        update(User).where(User.id == user.id).values(last_login_at=datetime.now(UTC))
    )
    await db.commit()

    token = create_access_token(
        sub=str(user.id), org_id=str(org.id), org_slug=org.slug
    )
    return TokenResponse(
        access_token=token,
        org_slug=org.slug,
        org_name=org.name,
        user_role=user.role,
    )


# ── Staff Login ───────────────────────────────────────────────────────────────

@router.post("/staff/login", response_model=StaffTokenResponse)
async def staff_login(body: StaffLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Strict rate limit for staff login — more sensitive target
    _check_rate_limit(f"staff:{request.client.host if request.client else 'unknown'}")
    staff = await db.scalar(
        select(StaffUser).where(StaffUser.email == body.email, StaffUser.is_active == True)
    )
    if not staff or not verify_password(body.password, staff.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_staff_token(staff_id=str(staff.id), email=staff.email)
    return StaffTokenResponse(
        access_token=token,
        staff_id=str(staff.id),
        email=staff.email,
    )


def _require_org_admin(user: User) -> None:
    if user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Owner or admin role required")


def _token_response(user: User, org: Organization) -> TokenResponse:
    token = create_access_token(sub=str(user.id), org_id=str(org.id), org_slug=org.slug)
    return TokenResponse(
        access_token=token,
        org_slug=org.slug,
        org_name=org.name,
        user_role=user.role,
    )


def _now_utc() -> datetime:
    return datetime.now(UTC)


async def _current_user_org(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Organization]:
    return await get_current_user_from_jwt(authorization=authorization, db=db)


# ── Invites ───────────────────────────────────────────────────────────────────

@router.post("/invites", response_model=InviteResponse)
async def create_invite(
    body: InviteCreateRequest,
    current: tuple[User, Organization] = Depends(_current_user_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_org_admin(user)
    await enforce_member_limit(org, db)

    existing_member = await db.scalar(
        select(User).where(User.org_id == org.id, User.email == str(body.email))
    )
    if existing_member:
        raise HTTPException(status_code=409, detail="Email is already a member of this workspace")

    existing_pending = await db.scalar(
        select(Invite).where(
            Invite.org_id == org.id,
            Invite.email == str(body.email),
            Invite.accepted_at.is_(None),
            Invite.expires_at > _now_utc(),
        )
    )
    if existing_pending:
        raise HTTPException(status_code=409, detail="Pending invite already exists for this email")

    invite = Invite(
        org_id=org.id,
        email=str(body.email),
        role=body.role,
        token=str(uuid.uuid4()),
        invited_by=user.id,
        expires_at=_now_utc() + timedelta(days=7),
    )
    db.add(invite)
    await db.flush()

    inviter_name = user.full_name or user.email
    if not email_service.send_invite_email(invite.email, org.name, inviter_name, invite.token, invite.role):
        await db.rollback()
        raise HTTPException(status_code=502, detail="Failed to send invite email")

    await db.commit()
    return InviteResponse(
        id=str(invite.id),
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
    )


@router.post("/invites/{token}/accept", response_model=TokenResponse)
async def accept_invite(
    token: str,
    body: InviteAcceptRequest,
    db: AsyncSession = Depends(get_db),
):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    invite = await db.scalar(select(Invite).where(Invite.token == token))
    if not invite or invite.accepted_at is not None or invite.expires_at <= _now_utc():
        raise HTTPException(status_code=400, detail="Invalid or expired invite")

    org = await db.get(Organization, invite.org_id)
    if not org:
        raise HTTPException(status_code=400, detail="Invite workspace no longer exists")

    existing_org_user = await db.scalar(
        select(User).where(User.org_id == invite.org_id, User.email == invite.email)
    )
    if existing_org_user:
        raise HTTPException(status_code=409, detail="Email is already a member of this workspace")

    existing_user = await db.scalar(select(User).where(User.email == invite.email))
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        org_id=invite.org_id,
        email=invite.email,
        password_hash=hash_password(body.password),
        role=invite.role,
        full_name=body.full_name,
    )
    db.add(user)
    invite.accepted_at = _now_utc()
    await db.commit()
    await db.refresh(user)

    email_service.send_welcome_email(user.email, user.full_name or "", org.name)
    return _token_response(user, org)


@router.get("/invites", response_model=list[InviteResponse])
async def list_pending_invites(
    current: tuple[User, Organization] = Depends(_current_user_org),
    db: AsyncSession = Depends(get_db),
):
    _user, org = current
    invites = (
        await db.scalars(
            select(Invite)
            .where(
                Invite.org_id == org.id,
                Invite.accepted_at.is_(None),
                Invite.expires_at > _now_utc(),
            )
            .order_by(Invite.created_at.desc())
        )
    ).all()
    return [
        InviteResponse(
            id=str(invite.id),
            email=invite.email,
            role=invite.role,
            expires_at=invite.expires_at,
        )
        for invite in invites
    ]


@router.delete("/invites/{invite_id}")
async def revoke_invite(
    invite_id: str,
    current: tuple[User, Organization] = Depends(_current_user_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    _require_org_admin(user)
    invite = await db.get(Invite, invite_id)
    if not invite or invite.org_id != org.id:
        raise HTTPException(status_code=404, detail="Invite not found")
    await db.delete(invite)
    await db.commit()
    return {"ok": True}


# ── Password reset ────────────────────────────────────────────────────────────

@router.post("/reset-password/request")
async def request_password_reset(
    body: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    org = await db.scalar(select(Organization).where(Organization.slug == body.org_slug))
    user = None
    if org:
        user = await db.scalar(
            select(User).where(User.org_id == org.id, User.email == str(body.email))
        )

    if user:
        token = str(uuid.uuid4())
        async with _password_reset_lock:
            _password_reset_tokens[token] = {
                "email": user.email,
                "org_slug": org.slug,
                "expires": _now_utc() + timedelta(hours=1),
            }
        email_service.send_password_reset_email(user.email, token)

    return {"message": "If an account exists, a password reset email has been sent"}


@router.post("/reset-password/confirm")
async def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    async with _password_reset_lock:
        record = _password_reset_tokens.get(body.token)
        if not record or record["expires"] <= _now_utc():
            _password_reset_tokens.pop(body.token, None)
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    org = await db.scalar(select(Organization).where(Organization.slug == record["org_slug"]))
    user = None
    if org:
        user = await db.scalar(select(User).where(User.org_id == org.id, User.email == record["email"]))
    if not user:
        async with _password_reset_lock:
            _password_reset_tokens.pop(body.token, None)
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.password_hash = hash_password(body.new_password)
    async with _password_reset_lock:
        _password_reset_tokens.pop(body.token, None)
    await db.commit()
    return {"message": "Password updated"}


# ── Profile settings ──────────────────────────────────────────────────────────

@router.patch("/profile", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdateRequest,
    current: tuple[User, Organization] = Depends(_current_user_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    if body.email is not None and str(body.email) != user.email:
        existing = await db.scalar(select(User).where(User.email == str(body.email), User.id != user.id))
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
        user.email = str(body.email)
    if body.full_name is not None:
        user.full_name = body.full_name

    await db.commit()
    await db.refresh(user)
    return ProfileResponse(
        id=str(user.id),
        org_id=str(org.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
    )


@router.patch("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current: tuple[User, Organization] = Depends(_current_user_org),
    db: AsyncSession = Depends(get_db),
):
    user, _org = current
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"message": "Password updated"}


# ── Dependencies ──────────────────────────────────────────────────────────────

async def get_current_org_from_api_key(
    x_api_key: str = Header(..., alias="x-api-key"),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Validates x-api-key header, returns org. For programmatic/worker use."""
    from app.auth import verify_api_key
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
    """Validates Bearer JWT, returns org. JWT must be of type 'user'."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:]
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "user":
        raise HTTPException(status_code=401, detail="Not a user token")
    org = await db.get(Organization, payload["org_id"])
    if not org:
        raise HTTPException(status_code=401, detail="Org not found")
    return org


async def get_current_user_from_jwt(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Organization]:
    """Returns (user, org) from JWT."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:]
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "user":
        raise HTTPException(status_code=401, detail="Not a user token")
    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    org = await db.get(Organization, payload["org_id"])
    if not org:
        raise HTTPException(status_code=401, detail="Org not found")
    return user, org


async def get_current_staff(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> StaffUser:
    """Validates staff Bearer JWT, returns StaffUser."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:]
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "staff":
        raise HTTPException(status_code=403, detail="Staff access required")
    staff = await db.get(StaffUser, payload["sub"])
    if not staff or not staff.is_active:
        raise HTTPException(status_code=401, detail="Staff account not found or inactive")
    return staff
