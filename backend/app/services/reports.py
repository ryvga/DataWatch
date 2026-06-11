import json
import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    CheckResult,
    DataSource,
    Incident,
    MonitoredTable,
    Organization,
    TableProfile,
)
from app.services.health_score import compute_health_score

logger = logging.getLogger(__name__)

_SUMMARY_KEY = "report:weekly_summary:{org_id}"
_SUMMARY_TTL = 8 * 24 * 3600  # 8 days — outlasts the weekly window slightly


def _redis():
    import redis
    from app.config import settings
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_cached_weekly_summary(org_id: str) -> dict | None:
    try:
        r = _redis()
        val = r.get(_SUMMARY_KEY.format(org_id=org_id))
        r.close()
        return json.loads(val) if val else None
    except Exception:
        return None


def cache_weekly_summary(org_id: str, summary: str) -> dict:
    payload = {"text": summary, "generated_at": datetime.now(UTC).isoformat()}
    try:
        r = _redis()
        r.setex(_SUMMARY_KEY.format(org_id=org_id), _SUMMARY_TTL, json.dumps(payload))
        r.close()
    except Exception as e:
        logger.warning("Failed to cache weekly summary: %s", e)
    return payload


def generate_ai_weekly_summary(report: dict, org_api_key: str | None = None, org_model: str | None = None) -> str:
    from openai import OpenAI
    from app.config import settings

    api_key = org_api_key or settings.OPENROUTER_API_KEY
    if not api_key:
        return ""

    top_checks = ", ".join(c["check_name"] for c in report.get("top_failing_checks", [])[:3]) or "none"
    tables_hit = ", ".join(report.get("tables_with_incidents", [])[:5]) or "none"
    sev = report.get("incidents_by_severity", {})

    system = (
        "You are a data reliability engineer. Your only job is to write executive summaries. "
        "Output ONLY the summary text — no preamble, no 'Sentence 1:', no 'Here is', no meta-commentary. "
        "Start directly with the first word of the summary."
    )

    user = (
        f"Write a 3-sentence executive summary from this weekly data quality report.\n\n"
        f"Health score: {report['health_score']:.0f}/100 (Grade {report['health_grade']})\n"
        f"Incidents: {report['incidents_total']} total, {report['incidents_open']} open, {report['incidents_resolved']} resolved\n"
        f"Severity: P1={sev.get('P1',0)}, P2={sev.get('P2',0)}, P3={sev.get('P3',0)}\n"
        f"Checks: {report['checks_passed']} passed, {report['checks_failed']} failed\n"
        f"Tables monitored: {report['tables_monitored']}\n"
        f"Top failing checks: {top_checks}\n"
        f"Tables with incidents: {tables_hit}\n\n"
        f"Rules: flowing prose only, no bullet points, mention specific numbers, end with the single most important action for next week."
    )

    client = OpenAI(api_key=api_key, base_url=settings.LLM_BASE_URL)
    response = client.chat.completions.create(
        model=org_model or settings.LLM_MODEL,
        max_tokens=256,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content.strip()


class ReportService:
    @staticmethod
    async def generate_weekly_report(
        org_id: UUID,
        db: AsyncSession,
        window_days: int = 7,
    ) -> dict:
        generated_at = datetime.now(UTC)
        window_start = generated_at - timedelta(days=window_days)

        org = (
            await db.scalars(select(Organization).where(Organization.id == org_id))
        ).first()
        if org is None:
            raise ValueError(f"Organization not found: {org_id}")

        incidents = (
            await db.scalars(
                select(Incident)
                .where(Incident.org_id == org_id)
                .where(Incident.created_at >= window_start)
            )
        ).all()

        tables = (
            await db.scalars(
                select(MonitoredTable)
                .join(DataSource, MonitoredTable.source_id == DataSource.id)
                .where(DataSource.org_id == org_id)
                .options(selectinload(MonitoredTable.data_source))
            )
        ).all()
        table_names_by_id = {table.id: table.table_name for table in tables}

        check_results = (
            await db.scalars(
                select(CheckResult)
                .join(MonitoredTable, CheckResult.table_id == MonitoredTable.id)
                .join(DataSource, MonitoredTable.source_id == DataSource.id)
                .where(DataSource.org_id == org_id)
                .where(CheckResult.checked_at >= window_start)
            )
        ).all()

        open_count = sum(1 for incident in incidents if incident.status != "resolved")
        resolved_count = sum(1 for incident in incidents if incident.status == "resolved")
        severity_counts = Counter(incident.severity for incident in incidents)
        check_type_counts = Counter(check.check_type for check in check_results)
        failing_check_counts = Counter(
            check.check_name for check in check_results if check.status == "failed"
        )

        checks_failed = sum(1 for check in check_results if check.status == "failed")
        checks_passed = sum(1 for check in check_results if check.status == "passed")
        health_inputs = [
            {"status": check.status, "severity": _severity_for_check(check, incidents)}
            for check in check_results
        ]
        health = compute_health_score(
            health_inputs,
            open_incidents=open_count,
            window_hours=window_days * 24,
        )

        tables_with_incidents = sorted(
            {
                table_names_by_id[incident.table_id]
                for incident in incidents
                if incident.table_id in table_names_by_id
            }
        )

        return {
            "report_type": "weekly",
            "org_id": org_id,
            "generated_at": generated_at,
            "window_days": window_days,
            "health_score": health.score,
            "health_grade": health.grade,
            "health_color": health.color,
            "incidents_total": len(incidents),
            "incidents_open": open_count,
            "incidents_resolved": resolved_count,
            "incidents_by_severity": dict(severity_counts),
            "checks_total": len(check_results),
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
            "checks_by_type": dict(check_type_counts),
            "tables_monitored": len(tables),
            "monitored_tables_detail": [
                {
                    "table_name": table.table_name,
                    "schema_name": table.schema_name,
                    "source_name": table.data_source.name,
                    "source_type": table.data_source.type,
                    "last_profiled_at": table.last_profiled_at,
                }
                for table in tables
            ],
            "tables_with_incidents": tables_with_incidents,
            "top_failing_checks": [
                {"check_name": check_name, "count": count}
                for check_name, count in failing_check_counts.most_common(5)
            ],
            "ai_summary": get_cached_weekly_summary(str(org_id)),
            "recommendations": _weekly_recommendations(
                open_count=open_count,
                checks_failed=checks_failed,
                stale_tables=[
                    table.table_name for table in tables if table.last_profiled_at is None
                ],
                health_score=health.score,
            ),
        }

    @staticmethod
    async def generate_incident_report(incident_id: UUID, db: AsyncSession) -> dict:
        incident = await db.scalar(
            select(Incident)
            .where(Incident.id == incident_id)
            .options(
                selectinload(Incident.table).selectinload(MonitoredTable.data_source)
            )
        )
        if incident is None:
            raise ValueError(f"Incident not found: {incident_id}")

        related_checks = (
            await db.scalars(
                select(CheckResult)
                .where(CheckResult.table_id == incident.table_id)
                .where(CheckResult.status == "failed")
                .order_by(desc(CheckResult.checked_at))
                .limit(20)
            )
        ).all()
        profile_snapshots = (
            await db.scalars(
                select(TableProfile)
                .where(TableProfile.table_id == incident.table_id)
                .order_by(desc(TableProfile.collected_at))
                .limit(2)
            )
        ).all()

        table = incident.table
        source = table.data_source

        return {
            "report_type": "incident",
            "incident_id": incident.id,
            "severity": incident.severity,
            "status": incident.status,
            "table_name": table.table_name,
            "source_name": source.name,
            "detected_at": incident.created_at,
            "resolved_at": incident.resolved_at,
            "fired_checks": _fired_checks(incident, related_checks),
            "llm_narration": incident.llm_narration,
            "client_safe_summary": _client_safe_summary(incident),
            "profile_snapshots": [
                _profile_snapshot(profile) for profile in profile_snapshots
            ],
            "debug_queries": _debug_queries(table),
        }


def _severity_for_check(check: CheckResult, incidents: list[Incident]) -> str:
    for incident in incidents:
        if incident.table_id == check.table_id and incident.status != "resolved":
            return incident.severity
    return "P3"


def _weekly_recommendations(
    open_count: int,
    checks_failed: int,
    stale_tables: list[str],
    health_score: float,
) -> list[str]:
    recommendations = []
    if open_count:
        recommendations.append(f"Investigate {open_count} open incident(s).")
    if checks_failed:
        recommendations.append(f"Review {checks_failed} failed check result(s).")
    if stale_tables:
        recommendations.append(
            f"Profile tables with no recent snapshot: {', '.join(stale_tables[:5])}."
        )
    if health_score < 80:
        recommendations.append("Prioritize recurring failures to improve data health.")
    if not recommendations:
        recommendations.append("No immediate action required.")
    return recommendations


def _fired_checks(incident: Incident, related_checks: list[CheckResult]) -> list:
    if related_checks:
        return [
            {
                "check_type": check.check_type,
                "check_name": check.check_name,
                "column_name": check.column_name,
                "status": check.status,
                "observed_value": check.observed_value,
                "expected_range": check.expected_range,
                "deviation_score": check.deviation_score,
                "checked_at": check.checked_at,
            }
            for check in related_checks
        ]
    return incident.fired_checks or []


def _client_safe_summary(incident: Incident) -> str:
    narration = incident.llm_narration or {}
    if isinstance(narration, str) and narration.strip():
        return narration.strip()
    if isinstance(narration, dict):
        for key in ("summary", "client_safe_summary", "impact_assessment"):
            value = narration.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return f"{incident.title}. Detailed AI narration pending."


def _profile_snapshot(profile: TableProfile) -> dict:
    return {
        "profile_id": profile.id,
        "collected_at": profile.collected_at,
        "row_count": profile.row_count,
        "freshness_seconds": profile.freshness_seconds,
        "schema_fingerprint": profile.schema_fingerprint,
        "column_metrics": profile.column_metrics,
        "profiling_duration_ms": profile.profiling_duration_ms,
        "error": profile.error,
    }


def _debug_queries(table: MonitoredTable) -> list[str]:
    qualified_name = f"{table.schema_name}.{table.table_name}"
    queries = [
        f"SELECT COUNT(*) AS row_count FROM {qualified_name};",
        f"SELECT * FROM {qualified_name} ORDER BY 1 DESC LIMIT 100;",
    ]
    if table.freshness_column:
        queries.append(
            f"SELECT MAX({table.freshness_column}) AS latest_freshness FROM {qualified_name};"
        )
    return queries
