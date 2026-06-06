"""
IncidentService — severity classification, deduplication, auto-resolve, title generation.
"""
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident
from app.services.anomaly import AnomalyResult

logger = logging.getLogger(__name__)


def classify_severity(failed_checks: list[AnomalyResult]) -> str:
    """
    P1: row_count_zero or freshness_sla_breach
    P2: schema_drift or ≥3 checks fail
    P3: 1-2 statistical failures
    """
    names = {c.check_name for c in failed_checks}
    custom_severities = [
        c.details.get("severity")
        for c in failed_checks
        if c.check_type == "custom_sql" and isinstance(c.details, dict)
    ]

    if "P1" in custom_severities:
        return "P1"
    if "P2" in custom_severities:
        return "P2"

    if "row_count_zero" in names or "freshness_sla_breach" in names:
        return "P1"
    if "schema_drift" in names or len(failed_checks) >= 3:
        return "P2"
    return "P3"


def generate_title(table_name: str, failed_checks: list[AnomalyResult]) -> str:
    names = {c.check_name for c in failed_checks}
    severity = classify_severity(failed_checks)
    custom_failures = [c for c in failed_checks if c.check_type == "custom_sql"]

    if custom_failures:
        monitor_name = custom_failures[0].check_name.replace("custom_monitor:", "", 1)
        if len(custom_failures) == 1:
            return f"[{severity}] {table_name} — custom monitor failed: {monitor_name}"
        return f"[{severity}] {table_name} — {len(custom_failures)} custom monitors failed"

    if "row_count_zero" in names:
        return f"[{severity}] {table_name} — row count dropped to 0"
    if "freshness_sla_breach" in names:
        return f"[{severity}] {table_name} — freshness SLA breached"
    if "schema_drift" in names:
        return f"[{severity}] {table_name} — schema drift detected"

    z_failures = [c for c in failed_checks if c.check_type == "z_score"]
    if z_failures:
        return f"[{severity}] {table_name} — {len(z_failures)} metric(s) anomalous (z-score)"

    return f"[{severity}] {table_name} — {len(failed_checks)} check(s) failed"


class IncidentService:

    async def create_or_update(
        self,
        db: AsyncSession,
        org_id,
        table,
        failed_checks: list[AnomalyResult],
        profile_id,
    ) -> Incident | None:
        if not failed_checks:
            return None

        fired = [
            {
                "check_type": c.check_type,
                "check_name": c.check_name,
                "column_name": c.column_name,
                "observed_value": c.observed_value,
                "deviation_score": c.deviation_score,
                "details": c.details,
            }
            for c in failed_checks
        ]

        # Check for existing open incident on this table
        existing = await db.scalar(
            select(Incident).where(
                Incident.table_id == table.id,
                Incident.status == "open",
            )
        )

        if existing:
            # Append new failed checks, avoid duplicates by check_name
            existing_names = {c["check_name"] for c in (existing.fired_checks or [])}
            new_fired = existing.fired_checks or []
            for c in fired:
                if c["check_name"] not in existing_names:
                    new_fired.append(c)
            existing.fired_checks = new_fired
            logger.info("Appended %d checks to incident %s", len(fired), existing.id)
            return existing

        # Create new incident
        severity = classify_severity(failed_checks)
        title = generate_title(table.table_name, failed_checks)

        incident = Incident(
            org_id=org_id,
            table_id=table.id,
            severity=severity,
            status="open",
            title=title,
            fired_checks=fired,
        )
        db.add(incident)
        await db.flush()

        logger.info("Created incident %s (%s) for table %s", incident.id, severity, table.table_name)
        return incident

    async def auto_resolve(
        self,
        db: AsyncSession,
        table,
        all_checks: list[AnomalyResult],
    ) -> bool:
        """
        If an open incident exists and ALL previously-fired check_names now pass,
        resolve the incident automatically.
        """
        existing = await db.scalar(
            select(Incident).where(
                Incident.table_id == table.id,
                Incident.status == "open",
            )
        )
        if not existing or not existing.fired_checks:
            return False

        previously_failed = {c["check_name"] for c in existing.fired_checks}
        now_passing = {c.check_name for c in all_checks if c.status == "passed"}

        if previously_failed.issubset(now_passing):
            existing.status = "resolved"
            existing.resolved_at = datetime.now(UTC)
            logger.info("Auto-resolved incident %s for table %s", existing.id, table.table_name)
            return True

        return False
