from datetime import UTC, datetime
from collections import defaultdict
import time
import threading

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
from app.models.organization import Organization
from app.models.user import ApiKey, StaffUser, User

router = APIRouter(prefix="/auth", tags=["auth"])

# ── Simple in-process rate limiter for login endpoints ────────────────────────
# Uses sliding window: max 10 attempts per IP per 60 seconds.
# Production should use Redis-backed rate limiting.
_RATE_LIMIT_WINDOW = 60   # seconds
_RATE_LIMIT_MAX = 10      # attempts per window
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock = threading.Lock()

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
