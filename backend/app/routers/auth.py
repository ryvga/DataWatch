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


async def get_current_user_from_jwt(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> tuple[User, Organization]:
    """Dependency: validates Bearer JWT, returns (user, org)."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:]
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    org = await db.get(Organization, payload["org_id"])
    if not org:
        raise HTTPException(status_code=401, detail="Org not found")
    return user, org
