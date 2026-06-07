from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.notification_prefs import UserNotificationPrefs
from app.models.organization import Organization
from app.models.user import User
from app.routers.auth import get_current_user_from_jwt

router = APIRouter(prefix="/api/v1/me", tags=["notifications"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class NotificationPrefsResponse(BaseModel):
    notify_assigned: bool
    notify_team: bool
    notify_status_change: bool
    daily_digest: bool
    digest_hour: int  # 0-23 UTC
    mute_until: datetime | None


class NotificationPrefsUpdate(BaseModel):
    notify_assigned: bool | None = None
    notify_team: bool | None = None
    notify_status_change: bool | None = None
    daily_digest: bool | None = None
    digest_hour: int | None = None  # 0-23 UTC
    mute_until: datetime | None = None

    @field_validator("digest_hour")
    @classmethod
    def validate_digest_hour(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 23):
            raise ValueError("digest_hour must be between 0 and 23")
        return v


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_create_prefs(
    user: User, org: Organization, db: AsyncSession
) -> UserNotificationPrefs:
    prefs = await db.scalar(
        select(UserNotificationPrefs).where(UserNotificationPrefs.user_id == user.id)
    )
    if not prefs:
        prefs = UserNotificationPrefs(user_id=user.id, org_id=org.id)
        db.add(prefs)
        await db.commit()
        await db.refresh(prefs)
    return prefs


def _prefs_response(prefs: UserNotificationPrefs) -> NotificationPrefsResponse:
    return NotificationPrefsResponse(
        notify_assigned=prefs.notify_assigned,
        notify_team=prefs.notify_team,
        notify_status_change=prefs.notify_status_change,
        daily_digest=prefs.daily_digest,
        digest_hour=prefs.digest_hour,
        mute_until=prefs.mute_until,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/notification-preferences", response_model=NotificationPrefsResponse)
async def get_notification_preferences(
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    prefs = await _get_or_create_prefs(user, org, db)
    return _prefs_response(prefs)


@router.patch("/notification-preferences", response_model=NotificationPrefsResponse)
async def update_notification_preferences(
    body: NotificationPrefsUpdate,
    current: tuple[User, Organization] = Depends(get_current_user_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    prefs = await _get_or_create_prefs(user, org, db)
    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(prefs, field, value)
    await db.commit()
    await db.refresh(prefs)
    return _prefs_response(prefs)
