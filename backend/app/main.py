import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import AsyncSessionLocal
from app.routers import alerts, auth, incidents, notifications, orgs, sources, tables, teams

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    from app.scheduler import start_scheduler
    await start_scheduler()
    yield
    # Shutdown
    from app.scheduler import stop_scheduler
    await stop_scheduler()


app = FastAPI(
    title="DataWatch API",
    version="0.1.0",
    description="Data quality monitoring platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else ["https://app.datawatch.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(orgs.router)
app.include_router(sources.router)
app.include_router(tables.router)
app.include_router(incidents.router)
app.include_router(alerts.router)
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
        logger.error(f"DB health check failed: {e}")

    try:
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        redis_status = "connected"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")

    from app.scheduler import scheduler
    return {
        "status": "ok",
        "db": db_status,
        "redis": redis_status,
        "scheduler_jobs": len(scheduler.get_jobs()),
    }
