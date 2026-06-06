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

CORE_RULE_CHECKS = {"row_count_zero", "freshness_sla_breach", "schema_drift"}


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
    def _check_names(self, checks: list[AnomalyResult] | list[dict]) -> set[str]:
        names = set()
        for check in checks:
            if isinstance(check, dict):
                name = check.get("check_name")
            else:
                name = check.check_name
            if name:
                names.add(name)
        return names

    def _iso_at(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    def _suppresses(self, incident: Incident, failed_checks: list[AnomalyResult]) -> bool:
        narration = incident.llm_narration or {}
        if not isinstance(narration, dict):
            return False

        now = datetime.now(UTC)
        suppress_until = None
        if incident.status == "muted":
            suppress_until = self._iso_at(narration.get("muted_until"))
        elif incident.status == "ignored":
            suppress_until = self._iso_at(narration.get("false_positive_until"))

        if not suppress_until or suppress_until <= now:
            return False

        previous = self._check_names(incident.fired_checks or [])
        current = self._check_names(failed_checks)
        return bool(previous and current and current.issubset(previous))

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

        suppressed = (await db.scalars(
            select(Incident).where(
                Incident.table_id == table.id,
                Incident.status.in_(["muted", "ignored"]),
            )
        )).all()
        for incident in suppressed:
            if self._suppresses(incident, failed_checks):
                logger.info("Suppressed duplicate incident for table %s due to %s incident %s", table.table_name, incident.status, incident.id)
                return None

        # Check for existing active incident on this table
        existing = await db.scalar(
            select(Incident).where(
                Incident.table_id == table.id,
                Incident.status.in_(["open", "acknowledged", "investigating"]),
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
        now_failed = {c.check_name for c in all_checks if c.status == "failed"}

        core_previous = previously_failed & CORE_RULE_CHECKS
        core_recovered = bool(core_previous) and core_previous.issubset(now_passing) and not (core_previous & now_failed)

        if previously_failed.issubset(now_passing) or core_recovered:
            existing.status = "resolved"
            existing.resolved_at = datetime.now(UTC)
            logger.info("Auto-resolved incident %s for table %s", existing.id, table.table_name)
            return True

        return False
