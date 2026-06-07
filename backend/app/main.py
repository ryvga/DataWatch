import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.config import settings
from app.database import AsyncSessionLocal
from app.routers import alerts, auth, billing, incidents, orgs, sources, tables
from app.routers import admin, reports, custom_monitors, notifications, teams

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


async def _seed_staff():
    """Bootstrap first staff account from env if none exist."""
    if not settings.STAFF_PASSWORD:
        return
    from app.auth import hash_password
    from app.models.user import StaffUser
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(select(StaffUser))
        if existing:
            return
        staff = StaffUser(
            email=settings.STAFF_EMAIL,
            password_hash=hash_password(settings.STAFF_PASSWORD),
            full_name=settings.STAFF_FULL_NAME,
        )
        db.add(staff)
        await db.commit()
        logger.info("Seeded initial staff user: %s", settings.STAFF_EMAIL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.scheduler import start_scheduler
    await _seed_staff()
    await start_scheduler()
    yield
    from app.scheduler import stop_scheduler
    await stop_scheduler()


app = FastAPI(
    title="Panopta API",
    version="0.2.0",
    description="Data quality monitoring SaaS platform",
    lifespan=lifespan,
)

# CORS: allow all in dev; in prod restrict to subdomains of BASE_DOMAIN
_origins = ["*"]
if settings.is_production:
    _origins = [
        f"https://{settings.BASE_DOMAIN}",
        f"https://*.{settings.BASE_DOMAIN}",
        f"https://{settings.ADMIN_SUBDOMAIN}.{settings.BASE_DOMAIN}",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://[a-z0-9-]+\.panopta\.app" if settings.is_production else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(billing.router)
app.include_router(orgs.router)
app.include_router(sources.router)
app.include_router(tables.router)
app.include_router(incidents.router)
app.include_router(alerts.router)
app.include_router(reports.router)
app.include_router(custom_monitors.router)
app.include_router(custom_monitors.org_router)
app.include_router(teams.router)
app.include_router(notifications.router)


@app.get("/health", tags=["infra"])
async def health():
    db_status = "disconnected"
    redis_status = "disconnected"

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error("DB health check failed: %s", e)

    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        redis_status = "connected"
    except Exception as e:
        logger.error("Redis health check failed: %s", e)

    from app.scheduler import scheduler
    return {
        "status": "ok",
        "db": db_status,
        "redis": redis_status,
        "scheduler_jobs": len(scheduler.get_jobs()),
    }
