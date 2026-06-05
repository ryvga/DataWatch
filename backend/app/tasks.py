"""
Celery tasks for DataWatch.
Tasks are synchronous entry points; async logic is wrapped with asyncio.run().
"""
import asyncio
import logging
from datetime import UTC, datetime

from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _dispose_engine():
    """Dispose SQLAlchemy asyncpg pool so it closes cleanly before the event loop exits."""
    from app.database import engine
    await engine.dispose()


def _run(coro):
    """Run a coroutine from a synchronous Celery task, then dispose the DB engine."""
    async def _wrapped():
        try:
            return await coro
        finally:
            await _dispose_engine()
    return asyncio.run(_wrapped())


@celery_app.task(
    bind=True,
    name="tasks.profile_table",
    max_retries=3,
    default_retry_delay=30,
)
def profile_table(self, table_id: str):
    """
    Profile a monitored table end-to-end.
    1. Load table + data_source from DB
    2. Decrypt credentials
    3. Create connector
    4. Run ProfilerService.profile()
    5. Persist TableProfile to DB
    6. Enqueue run_anomaly_checks
    """
    try:
        return _run(_profile_table_async(table_id))
    except Exception as exc:
        logger.error("profile_table failed for %s: %s", table_id, exc)
        raise self.retry(exc=exc)


async def _profile_table_async(table_id: str) -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.connectors.factory import ConnectorFactory
    from app.database import AsyncSessionLocal
    from app.models.data_source import DataSource
    from app.models.monitored_table import MonitoredTable
    from app.models.table_profile import TableProfile
    from app.services.crypto import decrypt_config
    from app.services.profiler import ProfilerService

    async with AsyncSessionLocal() as db:
        # Load table
        table = await db.scalar(
            select(MonitoredTable).where(MonitoredTable.id == table_id)
        )
        if not table:
            logger.error("MonitoredTable %s not found", table_id)
            return {"status": "error", "error": "table not found"}

        # Load source
        source = await db.get(DataSource, table.source_id)
        if not source:
            logger.error("DataSource for table %s not found", table_id)
            return {"status": "error", "error": "source not found"}

        # Rate limit check
        import redis as _redis_sync
        from app.config import settings
        from app.services.plans import check_and_increment_rate
        r_sync = _redis_sync.from_url(settings.REDIS_URL)
        org = await db.get(__import__("app.models.organization", fromlist=["Organization"]).Organization, source.org_id)
        allowed = check_and_increment_rate("profile_runs", str(source.org_id), org.plan if org else "free", r_sync)
        r_sync.close()
        if not allowed:
            logger.warning("Rate limit: profile_runs blocked for org %s", source.org_id)
            return {"status": "rate_limited", "table_id": table_id}

        # Decrypt + connect
        config = decrypt_config(source.connection_config["encrypted"], str(source.org_id))
        connector = ConnectorFactory.create(source.type, config)

        try:
            profiler = ProfilerService()
            result = await profiler.profile(
                connector=connector,
                schema=table.schema_name,
                table=table.table_name,
                freshness_column=table.freshness_column,
            )
        finally:
            await connector.close()

        # Persist
        profile = TableProfile(
            table_id=table.id,
            row_count=result.row_count,
            freshness_seconds=result.freshness_seconds,
            schema_fingerprint=result.schema_fingerprint,
            column_metrics=result.column_metrics,
            profiling_duration_ms=result.profiling_duration_ms,
            error=result.error,
        )
        db.add(profile)
        await db.flush()

        # Update last_profiled_at on the table
        table.last_profiled_at = datetime.now(UTC)
        await db.commit()

        # Enqueue anomaly checks (Day 4)
        from app.tasks import run_anomaly_checks
        run_anomaly_checks.delay(table_id, str(profile.id))

        log_payload = {
            "table_id": table_id,
            "profile_id": str(profile.id),
            "row_count": result.row_count,
            "duration_ms": result.profiling_duration_ms,
            "status": "error" if result.error else "ok",
        }
        logger.info("profile_table complete: %s", log_payload)
        return log_payload


@celery_app.task(name="tasks.run_anomaly_checks")
def run_anomaly_checks(table_id: str, profile_id: str):
    """Run all anomaly checks after a profile completes."""
    try:
        return _run(_run_anomaly_checks_async(table_id, profile_id))
    except Exception as exc:
        logger.error("run_anomaly_checks failed for table=%s: %s", table_id, exc)
        raise


async def _run_anomaly_checks_async(table_id: str, profile_id: str) -> dict:
    from datetime import timedelta, timezone

    import redis
    from sqlalchemy import desc, select

    from app.database import AsyncSessionLocal
    from app.models.check_result import CheckResult
    from app.models.monitored_table import MonitoredTable
    from app.models.table_profile import TableProfile
    from app.services.anomaly import (
        run_cardinality_checks,
        run_isolation_forest,
        run_row_growth_check,
        run_rule_checks,
        run_stl_check,
        run_z_score_checks,
    )
    from app.services.incident import IncidentService
    from app.config import settings

    async with AsyncSessionLocal() as db:
        # Load current profile
        profile = await db.get(TableProfile, profile_id)
        if not profile:
            return {"status": "error", "error": "profile not found"}

        table = await db.get(MonitoredTable, table_id)
        if not table:
            return {"status": "error", "error": "table not found"}

        # Load 30-day history (excluding current)
        cutoff = profile.collected_at - timedelta(days=30)
        history = (await db.scalars(
            select(TableProfile)
            .where(
                TableProfile.table_id == table_id,
                TableProfile.collected_at >= cutoff,
                TableProfile.id != profile_id,
                TableProfile.error.is_(None),
            )
            .order_by(TableProfile.collected_at)
        )).all()

        prev_profile = history[-1] if history else None

        # Run all checks
        r_client = None
        try:
            r_client = redis.from_url(settings.REDIS_URL)
        except Exception:
            pass

        all_checks = []
        all_checks += run_z_score_checks(profile, list(history), table.sensitivity)
        all_checks += run_rule_checks(profile, prev_profile, table)
        all_checks += run_isolation_forest(profile, list(history), table_id, r_client)
        all_checks += run_stl_check(profile, list(history))
        all_checks += run_cardinality_checks(profile, list(history))
        all_checks += run_row_growth_check(profile, list(history), table.sensitivity)

        if r_client:
            r_client.close()

        # Persist check_results
        for check in all_checks:
            cr = CheckResult(
                table_id=table.id,
                profile_id=profile.id,
                check_type=check.check_type,
                check_name=check.check_name,
                column_name=check.column_name,
                status=check.status,
                observed_value=check.observed_value,
                expected_range=check.expected_range,
                deviation_score=check.deviation_score,
            )
            db.add(cr)

        # Incident management
        failed = [c for c in all_checks if c.status == "failed"]
        svc = IncidentService()

        if failed:
            # Load org_id via data source
            from app.models.data_source import DataSource
            source = await db.get(DataSource, table.source_id)
            incident = await svc.create_or_update(
                db, source.org_id, table, failed, profile_id
            )
            if incident and incident.status == "open":
                from app.tasks import generate_llm_narration
                generate_llm_narration.delay(str(incident.id))
        else:
            await svc.auto_resolve(db, table, all_checks)

        await db.commit()

        return {
            "table_id": table_id,
            "profile_id": profile_id,
            "checks_run": len(all_checks),
            "failed": len(failed),
        }


@celery_app.task(
    bind=True,
    name="tasks.generate_llm_narration",
    max_retries=1,
    default_retry_delay=30,
)
def generate_llm_narration(self, incident_id: str):
    """Generate LLM narration for an incident, then dispatch alerts."""
    try:
        return _run(_generate_llm_narration_async(incident_id))
    except Exception as exc:
        logger.error("generate_llm_narration failed for %s: %s", incident_id, exc)
        raise self.retry(exc=exc)


async def _generate_llm_narration_async(incident_id: str) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.incident import Incident
    from app.services.llm import build_context, cache_narration, generate_narration, get_cached_narration

    # Check cache first
    cached = get_cached_narration(incident_id)
    if cached and "error" not in cached:
        logger.info("LLM narration cache hit for incident %s", incident_id)
        return {"status": "cached", "incident_id": incident_id}

    # Build context and call LLM — use per-org key if configured
    context_json = await build_context(incident_id)
    org_api_key: str | None = None
    org_model: str | None = None
    async with AsyncSessionLocal() as db:
        from app.models.incident import Incident as IncidentModel
        from app.models.organization import Organization
        from app.services.crypto import CryptoService
        inc = await db.get(IncidentModel, incident_id)
        if inc:
            org = await db.get(Organization, inc.org_id)
            if org and org.llm_api_key_encrypted:
                try:
                    org_api_key = CryptoService().decrypt_for_org(org.llm_api_key_encrypted, str(org.id))
                    org_model = org.llm_model
                except Exception:
                    pass

    narration = generate_narration(context_json, org_api_key=org_api_key, org_model=org_model)

    # Persist to DB + cache
    async with AsyncSessionLocal() as db:
        incident = await db.get(Incident, incident_id)
        if incident:
            incident.llm_narration = narration
            await db.commit()

    cache_narration(incident_id, narration)

    # Dispatch alerts after narration is ready
    send_alerts.delay(incident_id)

    return {
        "status": "ok" if "error" not in narration else "error",
        "incident_id": incident_id,
    }


@celery_app.task(name="tasks.cleanup_old_profiles")
def cleanup_old_profiles():
    """Daily Celery beat task: delete profiles older than plan retention window."""
    return _run(_cleanup_old_profiles_async())


async def _cleanup_old_profiles_async() -> dict:
    from sqlalchemy import text
    from app.database import AsyncSessionLocal
    from app.services.plans import PLAN_LIMITS

    deleted_total = 0
    async with AsyncSessionLocal() as db:
        for plan, limits in PLAN_LIMITS.items():
            retention = limits["retention_days"]
            if retention == -1:
                continue
            result = await db.execute(text(f"""
                DELETE FROM table_profiles
                WHERE collected_at < NOW() - INTERVAL '{retention} days'
                  AND table_id IN (
                    SELECT mt.id FROM monitored_tables mt
                    JOIN data_sources ds ON mt.source_id = ds.id
                    JOIN organizations o ON ds.org_id = o.id
                    WHERE o.plan = '{plan}'
                  )
            """))
            deleted = result.rowcount
            deleted_total += deleted
            if deleted:
                logger.info("Retention cleanup: deleted %d profiles for plan=%s (>%dd)", deleted, plan, retention)
        await db.commit()

    return {"deleted": deleted_total}


@celery_app.task(name="tasks.send_alerts")
def send_alerts(incident_id: str):
    """Dispatch alerts to all matching alert configs for this incident."""
    try:
        return _run(_send_alerts_async(incident_id))
    except Exception as exc:
        logger.error("send_alerts failed for incident %s: %s", incident_id, exc)
        raise


async def _send_alerts_async(incident_id: str) -> dict:
    from sqlalchemy import or_, select

    from app.database import AsyncSessionLocal
    from app.models.alert_config import AlertConfig
    from app.models.incident import Incident
    from app.services.alert import dispatch_alert
    from app.services.llm import get_cached_narration

    async with AsyncSessionLocal() as db:
        incident = await db.get(Incident, incident_id)
        if not incident:
            return {"status": "error", "error": "incident not found"}

        narration = get_cached_narration(incident_id) or incident.llm_narration

        # Get matching configs: org-wide OR table-specific
        configs = (await db.scalars(
            select(AlertConfig).where(
                AlertConfig.org_id == incident.org_id,
                AlertConfig.is_active == True,
                or_(
                    AlertConfig.table_id == incident.table_id,
                    AlertConfig.table_id.is_(None),
                ),
            )
        )).all()

        results = []
        for cfg in configs:
            ok = dispatch_alert(cfg, incident, narration)
            results.append({"config_id": str(cfg.id), "channel": cfg.channel, "sent": ok})

        return {"incident_id": incident_id, "alerts_dispatched": len(results), "results": results}
