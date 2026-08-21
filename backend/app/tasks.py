"""
Celery tasks for Panopta.
Tasks are synchronous entry points; async logic is wrapped with asyncio.run().
"""

import asyncio
import inspect
import logging
import uuid
from datetime import UTC, datetime

from app.worker import celery_app

logger = logging.getLogger(__name__)


def _profile_allows_downstream_checks(profile_result) -> bool:
    """An execution error is not a zero-row observation and must fail closed."""
    return not bool(profile_result.error)


async def _rollback_connector_transaction(connector) -> None:
    """Best-effort rollback for connectors that keep a transaction-bearing connection."""
    rollback = getattr(connector, "rollback", None)
    if not callable(rollback):
        conn = getattr(connector, "_conn", None)
        if conn is None or getattr(conn, "closed", False):
            return
        rollback = getattr(conn, "rollback", None)

    if not callable(rollback):
        return

    try:
        result = rollback()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        logger.warning(
            "Custom monitors: rollback after SQL error failed: %s",
            type(exc).__name__,
        )


async def _profile_connector_safely(
    *,
    source_type: str,
    config: dict,
    schema: str,
    table: str,
    freshness_column: str | None,
    table_id: str,
):
    """Run a profile while containing every connector lifecycle error."""
    from app.connectors.factory import ConnectorFactory
    from app.services.error_safety import safe_profile_error
    from app.services.profiler import ProfileResult, ProfilerService

    connector = None
    result = ProfileResult()
    try:
        connector = ConnectorFactory.create(source_type, config)
        result = await ProfilerService().profile(
            connector=connector,
            schema=schema,
            table=table,
            freshness_column=freshness_column,
        )
    except Exception as exc:
        logger.error(
            "Profile connector lifecycle failed for table %s: %s",
            table_id,
            type(exc).__name__,
        )
        result.error = safe_profile_error(exc)
    finally:
        if connector is not None:
            try:
                await connector.close()
            except Exception as exc:
                logger.warning(
                    "Profile connector close failed for table %s: %s",
                    table_id,
                    type(exc).__name__,
                )
                if result.error is None:
                    result.error = safe_profile_error(exc)
    return result


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
        logger.error("profile_table failed for %s: %s", table_id, type(exc).__name__)
        raise self.retry(exc=RuntimeError(f"profile task failed ({type(exc).__name__})"))


async def _profile_table_async(table_id: str) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.data_source import DataSource
    from app.models.monitored_table import MonitoredTable
    from app.models.table_profile import TableProfile
    from app.services.crypto import decrypt_config
    from app.services.table_autopilot import mark_profile_step

    async with AsyncSessionLocal() as db:
        # Load table
        table = await db.scalar(select(MonitoredTable).where(MonitoredTable.id == table_id))
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
        result = await _profile_connector_safely(
            source_type=source.type,
            config=config,
            schema=table.schema_name,
            table=table.table_name,
            freshness_column=table.freshness_column,
            table_id=table_id,
        )

        # Persist
        profile = TableProfile(
            table_id=table.id,
            row_count=result.row_count,
            freshness_seconds=result.freshness_seconds,
            schema_fingerprint=result.schema_fingerprint,
            column_metrics=result.column_metrics,
            profile_provenance=result.profile_provenance,
            profiling_duration_ms=result.profiling_duration_ms,
            error=result.error,
        )
        db.add(profile)
        await db.flush()

        # Update last_profiled_at on the table
        table.last_profiled_at = datetime.now(UTC)
        table.autopilot = mark_profile_step(
            table.autopilot,
            status="error" if result.error else "complete",
            profile_id=str(profile.id),
            error=result.error,
        )
        await db.commit()

        if not _profile_allows_downstream_checks(result):
            log_payload = {
                "table_id": table_id,
                "profile_id": str(profile.id),
                "row_count": result.row_count,
                "duration_ms": result.profiling_duration_ms,
                "status": "error",
            }
            logger.warning("profile_table stopped before checks: %s", log_payload)
            return log_payload

        # Enqueue anomaly checks (Day 4)
        from app.tasks import run_anomaly_checks

        run_anomaly_checks.delay(table_id, str(profile.id))

        # Enqueue custom monitors run
        from app.tasks import run_custom_monitors

        run_custom_monitors.delay(table_id, str(profile.id))

        # Enqueue typed DSL monitors on the same successful profile cadence.
        from app.tasks import run_dsl_monitors

        run_dsl_monitors.delay(table_id, str(profile.id))

        log_payload = {
            "table_id": table_id,
            "profile_id": str(profile.id),
            "row_count": result.row_count,
            "duration_ms": result.profiling_duration_ms,
            "status": "error" if result.error else "ok",
        }
        logger.info("profile_table complete: %s", log_payload)
        return log_payload


@celery_app.task(
    bind=True,
    name="tasks.bootstrap_table_autopilot",
    max_retries=5,
    default_retry_delay=60,
)
def bootstrap_table_autopilot(self, table_id: str):
    """Generate first-run baseline and AI monitor recommendations for a table."""
    try:
        return _run(_bootstrap_table_autopilot_async(table_id))
    except Exception as exc:
        logger.error("bootstrap_table_autopilot failed for %s: %s", table_id, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        # All retries exhausted — mark autopilot as failed so the UI shows a retry button
        _run(_mark_autopilot_failed_async(table_id, str(exc)))
        return {"status": "failed", "table_id": table_id, "error": str(exc)}


async def _bootstrap_table_autopilot_async(table_id: str) -> dict:
    from app.database import AsyncSessionLocal
    from app.models.data_source import DataSource
    from app.models.monitored_table import MonitoredTable
    from app.models.organization import Organization
    from app.services.table_autopilot import initial_autopilot_state, run_table_autopilot

    async with AsyncSessionLocal() as db:
        table = await db.get(MonitoredTable, table_id)
        if not table:
            return {"status": "error", "error": "table not found"}
        source = await db.get(DataSource, table.source_id)
        if not source:
            return {"status": "error", "error": "source not found"}
        org = await db.get(Organization, source.org_id)
        if not org:
            return {"status": "error", "error": "org not found"}

        if not table.autopilot:
            table.autopilot = initial_autopilot_state()

        state = await run_table_autopilot(db, table, source, org)
        await db.commit()
        return {
            "status": "ok",
            "table_id": table_id,
            "safe_monitors": len(state.get("safe_monitors") or []),
            "staged": len(state.get("recommendations") or []),
        }


async def _mark_autopilot_failed_async(table_id: str, error: str) -> None:
    from datetime import UTC, datetime
    from app.database import AsyncSessionLocal
    from app.models.monitored_table import MonitoredTable

    async with AsyncSessionLocal() as db:
        table = await db.get(MonitoredTable, table_id)
        if not table:
            return
        state = dict(table.autopilot or {})
        state["status"] = "failed"
        state["updated_at"] = datetime.now(UTC).isoformat()
        state["recommended_next_action"] = "Autopilot failed. Click 'Retry' to try again."
        steps = dict(state.get("steps") or {})
        steps["recommendations"] = {"status": "failed", "label": "AI monitor recommendations", "error": error}
        state["steps"] = steps
        table.autopilot = state
        await db.commit()


@celery_app.task(name="tasks.run_anomaly_checks")
def run_anomaly_checks(table_id: str, profile_id: str):
    """Run all anomaly checks after a profile completes."""
    try:
        return _run(_run_anomaly_checks_async(table_id, profile_id))
    except Exception as exc:
        logger.error("run_anomaly_checks failed for table=%s: %s", table_id, exc)
        raise


async def _run_anomaly_checks_async(table_id: str, profile_id: str) -> dict:
    from datetime import timedelta

    import redis
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.check_result import CheckResult
    from app.models.monitored_table import MonitoredTable
    from app.models.table_profile import TableProfile
    from app.services.anomaly import (
        run_cardinality_checks,
        run_cusum_check,
        run_distribution_drift_check,
        run_enum_drift_check,
        run_freshness_check,
        run_isolation_forest,
        run_mann_kendall_check,
        run_null_rate_trend_check,
        run_percentile_drift_check,
        run_row_growth_check,
        run_rule_checks,
        run_schema_change_check,
        run_stl_check,
        run_uniqueness_check,
        run_z_score_checks,
    )
    from app.services.incident import IncidentService
    from app.config import settings
    from app.models.data_source import DataSource
    from app.services.realtime import publish_event

    async with AsyncSessionLocal() as db:
        # Load current profile
        profile = await db.get(TableProfile, profile_id)
        if not profile:
            return {"status": "error", "error": "profile not found"}

        table = await db.get(MonitoredTable, table_id)
        if not table:
            return {"status": "error", "error": "table not found"}
        source = await db.get(DataSource, table.source_id)
        if not source:
            return {"status": "error", "error": "source not found"}

        # Load 30-day history (excluding current)
        cutoff = profile.collected_at - timedelta(days=30)
        history = (
            await db.scalars(
                select(TableProfile)
                .where(
                    TableProfile.table_id == table_id,
                    TableProfile.collected_at >= cutoff,
                    TableProfile.id != profile_id,
                    TableProfile.error.is_(None),
                )
                .order_by(TableProfile.collected_at)
            )
        ).all()

        prev_profile = history[-1] if history else None

        # Run all checks
        r_client = None
        try:
            r_client = redis.from_url(settings.REDIS_URL)
        except Exception:
            pass

        check_config = table.check_config or {}
        disabled = set(check_config.get("disabled_checks", []))
        disabled_cols = set(check_config.get("disabled_columns", []))

        all_checks = []
        sampled_native = (getattr(profile, "profile_provenance", None) or {}).get("profile_mode") == "sampled_native"
        if not sampled_native:
            if "z_score" not in disabled:
                all_checks += run_z_score_checks(profile, list(history), table.sensitivity)
            if "isolation_forest" not in disabled:
                all_checks += run_isolation_forest(profile, list(history), table_id, r_client)
            if "stl_seasonal" not in disabled:
                all_checks += run_stl_check(profile, list(history))
            if "cardinality_drop" not in disabled:
                all_checks += run_cardinality_checks(profile, list(history))
            if "row_growth" not in disabled:
                all_checks += run_row_growth_check(profile, list(history), table.sensitivity)
            if "enum_drift" not in disabled:
                all_checks += run_enum_drift_check(profile, list(history))
            if "distribution_drift" not in disabled:
                all_checks += run_distribution_drift_check(profile, list(history))
            if "null_rate_trend" not in disabled:
                all_checks += run_null_rate_trend_check(profile, list(history))
            all_checks += run_schema_change_check(profile, list(history))
            if "uniqueness" not in disabled:
                all_checks += run_uniqueness_check(profile, list(history))
            if "cusum" not in disabled:
                all_checks += run_cusum_check(profile, list(history))
            if "mann_kendall" not in disabled:
                all_checks += run_mann_kendall_check(profile, list(history))
            if "percentile_drift" not in disabled:
                all_checks += run_percentile_drift_check(profile, list(history))
        all_checks += run_rule_checks(profile, prev_profile, table)
        all_checks += run_freshness_check(profile, table)

        # Filter out disabled columns
        if disabled_cols:
            all_checks = [c for c in all_checks if not (c.column_name and c.column_name in disabled_cols)]

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

        incident = None
        auto_resolved = False
        if failed:
            auto_resolved = await svc.auto_resolve(db, table, all_checks)
            incident = await svc.create_or_update(db, source.org_id, table, failed, profile_id)
            if incident and incident.status == "open":
                from app.tasks import generate_llm_narration

                generate_llm_narration.delay(str(incident.id))
        else:
            auto_resolved = await svc.auto_resolve(db, table, all_checks)

        await db.commit()

        await publish_event(
            str(source.org_id),
            "profile.completed",
            {"tableId": str(table.id), "profileId": str(profile.id), "failed": len(failed), "checks": len(all_checks)},
        )
        if incident is not None:
            await publish_event(
                str(source.org_id),
                "incident.updated",
                {
                    "incidentId": str(incident.id),
                    "tableId": str(table.id),
                    "status": incident.status,
                    "severity": incident.severity,
                },
            )
        elif auto_resolved:
            await publish_event(
                str(source.org_id),
                "incident.updated",
                {"tableId": str(table.id), "status": "resolved", "source": "auto_resolve"},
            )

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


@celery_app.task(name="tasks.run_custom_monitors")
def run_custom_monitors(table_id: str, profile_id: str | None = None):
    """Run all active custom SQL monitors for a table after profiling."""
    try:
        return _run(_run_custom_monitors_async(table_id, profile_id))
    except Exception as exc:
        logger.error("run_custom_monitors failed for table=%s: %s", table_id, exc)


async def _run_custom_monitors_async(table_id: str, profile_id: str | None = None) -> dict:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.check_result import CheckResult
    from app.models.custom_monitor import CustomMonitor
    from app.models.data_source import DataSource
    from app.models.monitored_table import MonitoredTable
    from app.connectors.factory import ConnectorFactory
    from app.services.anomaly import AnomalyResult
    from app.services.crypto import decrypt_config
    from app.services.incident import IncidentService
    from app.services.legacy_sql_monitor import (
        execute_legacy_monitor,
        validate_legacy_sql,
    )

    async with AsyncSessionLocal() as db:
        table = await db.get(MonitoredTable, table_id)
        if not table:
            return {"status": "error", "error": "table not found"}

        monitors = (
            await db.scalars(
                select(CustomMonitor).where(
                    CustomMonitor.table_id == table_id,
                    CustomMonitor.is_active.is_(True),
                    CustomMonitor.run_on_profile.is_(True),
                )
            )
        ).all()

        if not monitors:
            return {"status": "ok", "run": 0}

        source = await db.get(DataSource, table.source_id)
        if not source:
            return {"status": "error", "error": "source not found"}

        try:
            config = decrypt_config(source.connection_config["encrypted"], str(source.org_id))
            connector = ConnectorFactory.create(source.type, config)
        except Exception as exc:
            logger.error("Custom monitors: connector failed for table %s: %s", table_id, exc)
            return {"status": "error", "error": str(exc)}

        ran, failed = 0, 0
        now = datetime.now(UTC)
        check_results: list[AnomalyResult] = []
        profile_uuid = uuid.UUID(profile_id) if profile_id else None
        try:
            for m in monitors:
                try:
                    query = validate_legacy_sql(
                        m.sql_query,
                        m.severity,
                        source_type=source.type,
                        target_schema=table.schema_name,
                        target_table=table.table_name,
                    )
                    _, violation_count = await execute_legacy_monitor(connector, query)
                    passed = violation_count == 0
                    m.last_run_at = now
                    m.last_result = {
                        "violation_count": violation_count,
                        "passed": passed,
                        "executed_at": now.isoformat(),
                    }
                    check = AnomalyResult(
                        check_type="custom_sql",
                        check_name=f"custom_monitor:{m.name}",
                        column_name=None,
                        status="passed" if passed else "failed",
                        observed_value=float(violation_count),
                        expected_range={"low": 0, "high": 0},
                        deviation_score=float(violation_count),
                        details={"monitor_id": str(m.id), "severity": m.severity},
                    )
                    check_results.append(check)
                    db.add(
                        CheckResult(
                            table_id=table.id,
                            profile_id=profile_uuid,
                            check_type=check.check_type,
                            check_name=check.check_name,
                            column_name=check.column_name,
                            status=check.status,
                            observed_value=check.observed_value,
                            expected_range=check.expected_range,
                            deviation_score=check.deviation_score,
                        )
                    )
                    ran += 1
                    if not passed:
                        failed += 1
                except Exception as exc:
                    logger.warning("Custom monitor %s failed: %s", m.id, exc)
                    await _rollback_connector_transaction(connector)
                    m.last_run_at = now
                    m.last_result = {"error": str(exc), "executed_at": now.isoformat()}
        finally:
            await connector.close()

        source = await db.get(DataSource, table.source_id)
        svc = IncidentService()
        failed_checks = [c for c in check_results if c.status == "failed"]
        if failed_checks and source:
            await svc.auto_resolve(db, table, check_results)
            incident = await svc.create_or_update(db, source.org_id, table, failed_checks, profile_id)
            if incident and incident.status == "open":
                from app.tasks import generate_llm_narration

                generate_llm_narration.delay(str(incident.id))
        elif check_results:
            await svc.auto_resolve(db, table, check_results)

        await db.commit()
        return {"status": "ok", "run": ran, "failed": failed}


def _monitor_execution_error_code(error) -> str:
    """Map internal execution failures to the persisted, secret-free contract."""
    code = getattr(error, "code", None)
    if code == "execution_timeout":
        return "execution_timeout"
    if code in {
        "connector_execution_not_supported",
        "query_concurrency_exceeded",
        "query_lease_unavailable",
        "scan_budget_exceeded",
        "scan_budget_not_supported",
        "document_scan_budget_exceeded",
        "row_scan_budget_exceeded",
    }:
        return code
    return "execution_failed"


async def _bridge_dsl_incident(db, *, source, table, monitor, run, profile_id):
    """Translate a typed policy transition into the existing incident lifecycle."""
    from app.models.monitor import MonitorRevision
    from app.services.anomaly import AnomalyResult
    from app.services.incident import IncidentService
    from app.services.monitor_dsl import load_persisted_definition

    result = run.result or {}
    action = result.get("incidentAction")
    if action not in {"open", "reminder_due", "resolve"}:
        return None

    definition = load_persisted_definition((await db.get(MonitorRevision, run.revision_id)).definition)
    severity = definition.spec.policy.severity
    check_name = f"dsl_monitor:{monitor.name}"
    check = AnomalyResult(
        check_type="monitor_dsl",
        check_name=check_name,
        column_name=None,
        status="failed" if result.get("rawState") == "breached" else "passed",
        observed_value=None,
        expected_range=None,
        deviation_score=None,
        details={"monitor_id": str(monitor.id), "severity": severity},
    )
    service = IncidentService()
    if action == "resolve":
        await service.auto_resolve(db, table, [check])
        return None
    incident = await service.create_or_update(db, source.org_id, table, [check], profile_id)
    if incident and incident.status == "open":
        from app.tasks import generate_llm_narration

        generate_llm_narration.delay(str(incident.id))
    return incident


async def _run_one_dsl_monitor(
    monitor_id: str,
    *,
    profile_id: str | None = None,
    client_idempotency_key: str | None = None,
) -> dict:
    """Reserve, execute, finalize, and bridge one active typed monitor."""
    from app.connectors.factory import ConnectorFactory
    from app.database import AsyncSessionLocal
    from app.models.data_source import DataSource
    from app.models.monitor import Monitor, MonitorRevision
    from app.models.monitored_table import MonitoredTable
    from app.services.crypto import decrypt_config
    from app.services.monitor_dsl import load_persisted_definition
    from app.services.monitor_planning import compile_monitor_plan
    from app.services.monitor_run_service import (
        MonitorRunError,
        RunRequest,
        claim_next_run,
        finalize_error,
        finalize_success,
        reserve_run,
    )
    from app.services.monitor_runtime import execute_monitor_plan
    from app.services.query_lease import source_query_lease
    from app.services.realtime import publish_event
    from app.services.schema_binding import build_relation_binding

    async with AsyncSessionLocal() as db:
        monitor = await db.get(Monitor, monitor_id)
        if not monitor or monitor.mode != "dsl" or monitor.status != "active" or not monitor.active_revision_id:
            return {"status": "skipped", "reason": "monitor_not_active", "monitor_id": monitor_id}
        revision = await db.get(MonitorRevision, monitor.active_revision_id)
        table = await db.get(MonitoredTable, monitor.table_id)
        source = await db.get(DataSource, table.source_id) if table else None
        if not revision or not table or not source:
            return {"status": "error", "reason": "monitor_context_invalid", "monitor_id": monitor_id}

        now = datetime.now(UTC)
        request = RunRequest(
            org_id=monitor.org_id,
            monitor_id=monitor.id,
            revision_id=revision.id,
            trigger_type="on_profile" if profile_id else "manual",
            profile_id=uuid.UUID(profile_id) if profile_id else None,
            client_idempotency_key=client_idempotency_key,
        )
        try:
            reservation = await reserve_run(db, request, now=now)
        except MonitorRunError as exc:
            logger.warning("DSL monitor reservation failed for %s: %s", monitor_id, exc.code)
            return {"status": "error", "reason": exc.code, "monitor_id": monitor_id}
        await db.commit()

        claim = await claim_next_run(db, org_id=monitor.org_id, run_id=reservation.run_id, now=now)
        if claim is None:
            run = await db.get(__import__("app.models.monitor", fromlist=["MonitorRun"]).MonitorRun, reservation.run_id)
            return {"status": "skipped", "reason": "not_claimed", "run_id": str(run.id)}
        await db.commit()

        connector = None
        try:
            config = decrypt_config(source.connection_config["encrypted"], str(source.org_id))
            connector = ConnectorFactory.create(source.type, config)
            profile_schema_fingerprint = None
            if profile_id:
                from app.models.table_profile import TableProfile

                profile = await db.get(TableProfile, profile_id)
                profile_schema_fingerprint = profile.schema_fingerprint if profile else None
            relation = build_relation_binding(
                asset_id=table.id,
                source_type=source.type,
                schema_name=table.schema_name,
                table_name=table.table_name,
                ddl=table.dbt_model_yaml,
                latest_schema_fingerprint=profile_schema_fingerprint,
            )
            plan = compile_monitor_plan(
                load_persisted_definition(revision.definition),
                relation=relation,
                ddl=table.dbt_model_yaml,
            )
            async with source_query_lease(
                str(source.org_id),
                str(source.id),
                ttl_seconds=plan.timeout_seconds + 30,
            ):
                measurements = await execute_monitor_plan(connector, plan)
        except Exception as exc:
            try:
                await finalize_error(
                    db,
                    org_id=monitor.org_id,
                    claim=claim,
                    error_code=_monitor_execution_error_code(exc),
                    now=datetime.now(UTC),
                )
                await db.commit()
            except MonitorRunError:
                await db.rollback()
            return {"status": "error", "reason": _monitor_execution_error_code(exc), "run_id": str(claim.run_id)}
        finally:
            if connector is not None:
                try:
                    await connector.close()
                except Exception:
                    logger.warning("DSL monitor connector close failed for %s", monitor_id)

        run = await finalize_success(
            db,
            org_id=monitor.org_id,
            claim=claim,
            plan=plan,
            definition_hash=revision.definition_hash,
            measurements=measurements,
            now=datetime.now(UTC),
        )
        await _bridge_dsl_incident(
            db,
            source=source,
            table=table,
            monitor=monitor,
            run=run,
            profile_id=profile_id,
        )
        await db.commit()
        await publish_event(
            str(source.org_id),
            "monitor.run.completed",
            {
                "monitorId": str(monitor.id),
                "tableId": str(table.id),
                "runId": str(run.id),
                "status": run.status,
                "profileId": profile_id,
            },
        )
        return {"status": run.status, "run_id": str(run.id), "result": run.result}


@celery_app.task(name="tasks.run_dsl_monitor")
def run_dsl_monitor(monitor_id: str, client_idempotency_key: str):
    """Execute one manually requested active DSL monitor."""
    try:
        return _run(_run_one_dsl_monitor(monitor_id, client_idempotency_key=client_idempotency_key))
    except Exception as exc:
        logger.error("run_dsl_monitor failed for monitor=%s: %s", monitor_id, type(exc).__name__)
        raise


@celery_app.task(name="tasks.run_dsl_monitors")
def run_dsl_monitors(table_id: str, profile_id: str):
    """Execute all active typed DSL monitors after a successful profile."""
    try:
        return _run(_run_dsl_monitors_async(table_id, profile_id))
    except Exception as exc:
        logger.error("run_dsl_monitors failed for table=%s: %s", table_id, type(exc).__name__)
        raise


async def _run_dsl_monitors_async(table_id: str, profile_id: str) -> dict:
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.monitor import Monitor, MonitorRevision

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Monitor.id, MonitorRevision.definition)
                .join(
                    MonitorRevision,
                    (MonitorRevision.monitor_id == Monitor.id) & (MonitorRevision.revision == Monitor.current_revision),
                )
                .where(
                    Monitor.table_id == table_id,
                    Monitor.mode == "dsl",
                    Monitor.status == "active",
                )
            )
        ).all()
        monitor_ids = [
            monitor_id
            for monitor_id, definition_payload in rows
            if definition_payload.get("spec", {}).get("trigger", {}).get("type", "on_profile") == "on_profile"
        ]
    results = [await _run_one_dsl_monitor(str(monitor_id), profile_id=profile_id) for monitor_id in monitor_ids]
    return {"status": "ok", "table_id": table_id, "profile_id": profile_id, "runs": results}


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
            result = await db.execute(
                text(f"""
                DELETE FROM table_profiles
                WHERE collected_at < NOW() - INTERVAL '{retention} days'
                  AND table_id IN (
                    SELECT mt.id FROM monitored_tables mt
                    JOIN data_sources ds ON mt.source_id = ds.id
                    JOIN organizations o ON ds.org_id = o.id
                    WHERE o.plan = '{plan}'
                  )
            """)
            )
            deleted = result.rowcount
            deleted_total += deleted
            if deleted:
                logger.info("Retention cleanup: deleted %d profiles for plan=%s (>%dd)", deleted, plan, retention)
        await db.commit()

    return {"deleted": deleted_total}


@celery_app.task(name="tasks.generate_weekly_summaries")
def generate_weekly_summaries():
    """Weekly Celery beat task: generate AI summary for every org that has an LLM key."""
    return _run(_generate_weekly_summaries_async())


async def _generate_weekly_summaries_async() -> dict:
    from app.database import AsyncSessionLocal
    from app.models.organization import Organization
    from app.services.reports import ReportService, generate_ai_weekly_summary, cache_weekly_summary
    from app.services.crypto import CryptoService
    from sqlalchemy import select

    generated = 0
    failed = 0
    async with AsyncSessionLocal() as db:
        orgs = (await db.scalars(select(Organization))).all()
        for org in orgs:
            try:
                report = await ReportService.generate_weekly_report(org.id, db)
                org_api_key = None
                org_model = None
                if org.llm_api_key_encrypted:
                    try:
                        org_api_key = CryptoService().decrypt_for_org(org.llm_api_key_encrypted, str(org.id))
                        org_model = org.llm_model
                    except Exception:
                        pass
                text = generate_ai_weekly_summary(report, org_api_key=org_api_key, org_model=org_model)
                if text:
                    cache_weekly_summary(str(org.id), text)
                    generated += 1
            except Exception as e:
                logger.warning("Weekly summary failed for org %s: %s", org.id, e)
                failed += 1

    logger.info("Weekly summaries: generated=%d failed=%d", generated, failed)
    return {"generated": generated, "failed": failed}


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
    from app.services.realtime import publish_event

    async with AsyncSessionLocal() as db:
        incident = await db.get(Incident, incident_id)
        if not incident:
            return {"status": "error", "error": "incident not found"}

        narration = get_cached_narration(incident_id) or incident.llm_narration

        # Get matching configs: org-wide OR table-specific
        configs = (
            await db.scalars(
                select(AlertConfig).where(
                    AlertConfig.org_id == incident.org_id,
                    AlertConfig.is_active.is_(True),
                    or_(
                        AlertConfig.table_id == incident.table_id,
                        AlertConfig.table_id.is_(None),
                    ),
                )
            )
        ).all()

        results = []
        for cfg in configs:
            ok = dispatch_alert(cfg, incident, narration)
            results.append({"config_id": str(cfg.id), "channel": cfg.channel, "sent": ok})

        await publish_event(
            str(incident.org_id),
            "alert.dispatched",
            {"incidentId": str(incident.id), "results": results},
        )

        return {"incident_id": incident_id, "alerts_dispatched": len(results), "results": results}


@celery_app.task(name="tasks.notify_incident_assignment")
def notify_incident_assignment(incident_id: str):
    """Placeholder: send notifications when an incident is assigned to a user or team.
    Checks UserNotificationPrefs for recipients and dispatches accordingly.
    Full implementation depends on alert channel config."""
    logger.info("notify_incident_assignment: incident_id=%s (stub, no-op)", incident_id)
