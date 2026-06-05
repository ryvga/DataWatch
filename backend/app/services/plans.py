"""
Plan enforcement and rate limiting.

Plans: free | starter | growth | enterprise
-1 = unlimited
"""
import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

PLAN_LIMITS: dict[str, dict] = {
    "free":       {"sources": 1,  "tables": 5,   "members": 3,   "retention_days": 7,   "profile_runs_day": 500,  "llm_calls_day": 20},
    "starter":    {"sources": 3,  "tables": 50,  "members": 10,  "retention_days": 90,  "profile_runs_day": 2000, "llm_calls_day": 100},
    "growth":     {"sources": -1, "tables": -1,  "members": -1,  "retention_days": 365, "profile_runs_day": -1,   "llm_calls_day": -1},
    "enterprise": {"sources": -1, "tables": -1,  "members": -1,  "retention_days": -1,  "profile_runs_day": -1,   "llm_calls_day": -1},
}

UPGRADE_URL = "https://datawatch.io/pricing"


def get_limits(plan: str) -> dict:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


async def enforce_source_limit(org, db: AsyncSession) -> None:
    from app.models.data_source import DataSource
    limits = get_limits(org.plan)
    max_sources = limits["sources"]
    if max_sources == -1:
        return
    count = await db.scalar(
        select(func.count()).select_from(DataSource)
        .where(DataSource.org_id == org.id, DataSource.status != "paused")
    )
    if count >= max_sources:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "plan_limit_exceeded",
                "resource": "sources",
                "limit": max_sources,
                "current": count,
                "plan": org.plan,
                "upgrade_url": UPGRADE_URL,
            },
        )


async def enforce_table_limit(org, db: AsyncSession) -> None:
    from app.models.data_source import DataSource
    from app.models.monitored_table import MonitoredTable
    limits = get_limits(org.plan)
    max_tables = limits["tables"]
    if max_tables == -1:
        return
    source_ids = (await db.scalars(
        select(DataSource.id).where(DataSource.org_id == org.id)
    )).all()
    count = await db.scalar(
        select(func.count()).select_from(MonitoredTable)
        .where(MonitoredTable.source_id.in_(source_ids), MonitoredTable.is_active == True)
    )
    if count >= max_tables:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "plan_limit_exceeded",
                "resource": "tables",
                "limit": max_tables,
                "current": count,
                "plan": org.plan,
                "upgrade_url": UPGRADE_URL,
            },
        )


async def enforce_member_limit(org, db: AsyncSession) -> None:
    from app.models.invite import Invite
    from app.models.user import User

    limits = get_limits(org.plan)
    max_members = limits["members"]
    if max_members == -1:
        return

    now = datetime.now(UTC)
    active_users = await db.scalar(
        select(func.count()).select_from(User).where(User.org_id == org.id)
    ) or 0
    pending_invites = await db.scalar(
        select(func.count()).select_from(Invite).where(
            Invite.org_id == org.id,
            Invite.accepted_at.is_(None),
            Invite.expires_at > now,
        )
    ) or 0
    current = active_users + pending_invites
    if current >= max_members:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "plan_limit_exceeded",
                "resource": "members",
                "limit": max_members,
                "current": current,
                "plan": org.plan,
                "upgrade_url": UPGRADE_URL,
            },
        )


# ── Redis rate limiting ────────────────────────────────────────────────────────

def _rate_key(kind: str, org_id: str) -> str:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"rate:{kind}:{org_id}:{today}"


def check_and_increment_rate(kind: str, org_id: str, plan: str, redis_client) -> bool:
    """
    Returns True if allowed, False if rate limit exceeded.
    Increments counter on allow.
    kind: 'profile_runs' | 'llm_calls'
    """
    limits = get_limits(plan)
    max_val = limits.get(f"{kind}_day", -1)
    if max_val == -1:
        return True

    key = _rate_key(kind, org_id)
    current = redis_client.get(key)
    current = int(current) if current else 0

    if current >= max_val:
        logger.warning("Rate limit exceeded: %s org=%s plan=%s (%d/%d)", kind, org_id, plan, current, max_val)
        return False

    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, 86400)
    pipe.execute()
    return True
