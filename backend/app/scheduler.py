"""
APScheduler — one interval job per active monitored table.
Embedded in FastAPI lifespan. Enqueues Celery tasks (no direct DB writes).

Crash recovery: on startup, any table whose last_profiled_at is > 2x its
interval ago gets an immediate enqueue.
"""
import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


# ── Job action ────────────────────────────────────────────────────────────────

def _enqueue_profile(table_id: str) -> None:
    """Called by APScheduler — synchronously enqueues a Celery task."""
    from app.tasks import profile_table
    task = profile_table.delay(table_id)
    logger.info("Scheduled profile enqueued: table=%s task=%s", table_id, task.id)


# ── Public API ────────────────────────────────────────────────────────────────

def job_id(table_id: str) -> str:
    return f"table_{table_id}"


def add_table_job(table_id: str, interval_minutes: int) -> None:
    jid = job_id(table_id)
    if scheduler.get_job(jid):
        scheduler.reschedule_job(jid, trigger=IntervalTrigger(minutes=interval_minutes))
        logger.info("Rescheduled job %s to %d min", jid, interval_minutes)
    else:
        scheduler.add_job(
            _enqueue_profile,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=jid,
            args=[table_id],
            replace_existing=True,
            misfire_grace_time=120,
        )
        logger.info("Added scheduler job %s (%d min)", jid, interval_minutes)


def remove_table_job(table_id: str) -> None:
    jid = job_id(table_id)
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
        logger.info("Removed scheduler job %s", jid)


def reschedule_table_job(table_id: str, interval_minutes: int) -> None:
    add_table_job(table_id, interval_minutes)


# ── Startup ───────────────────────────────────────────────────────────────────

async def start_scheduler() -> None:
    """Load all active tables from DB, schedule jobs, do crash recovery."""
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.monitored_table import MonitoredTable
    from app.tasks import profile_table

    scheduler.start()
    logger.info("APScheduler started")

    async with AsyncSessionLocal() as db:
        tables = (await db.scalars(
            select(MonitoredTable).where(MonitoredTable.is_active == True)
        )).all()

    now = datetime.now(UTC)
    immediate = []

    for table in tables:
        add_table_job(str(table.id), table.check_interval_minutes)

        # Crash recovery: if overdue by more than 2x interval, enqueue immediately
        if table.last_profiled_at is None:
            immediate.append(table)
        else:
            last = table.last_profiled_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            overdue_threshold = last + timedelta(minutes=table.check_interval_minutes * 2)
            if now > overdue_threshold:
                immediate.append(table)

    for table in immediate:
        try:
            profile_table.delay(str(table.id))
            logger.info("Crash recovery: immediate profile enqueued for table %s", table.id)
        except Exception as e:
            logger.warning("Could not enqueue recovery profile for %s: %s", table.id, e)

    logger.info("Scheduler loaded %d jobs, %d immediate recovery runs", len(tables), len(immediate))


async def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
