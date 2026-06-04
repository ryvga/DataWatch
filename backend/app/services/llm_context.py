"""
LLM context assembly — compact format, token-budget aware.

Target: < 3000 tokens total input.
Budget:
  system prompt:          ~200 tokens
  incident + checks:      ~400 tokens
  schema:                 ~300 tokens (max 20 cols)
  profile history table:  ~600 tokens (14 days, 5 metrics)
  dbt YAML:               ~500 tokens (if present)
  buffer:                 ~500 tokens
"""
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select

logger = logging.getLogger(__name__)

MAX_COLUMNS = 20
HISTORY_DAYS = 14
MAX_METRICS_PER_COL = 3  # null_rate, mean, stddev


def _format_checks(fired_checks: list) -> str:
    """Compact single-line format per check to save tokens."""
    if not fired_checks:
        return "  (none)"
    lines = []
    for c in fired_checks:
        obs = c.get("observed_value")
        score = c.get("deviation_score")
        obs_str = f"observed={obs}" if obs is not None else ""
        score_str = f"deviation={score:.2f}" if score is not None else ""
        parts = [p for p in [obs_str, score_str] if p]
        lines.append(f"  FAIL: {c['check_name']} | {' | '.join(parts)}")
    return "\n".join(lines)


def _format_profile_history(profiles: list, fired_check_names: set) -> str:
    """
    Compact TSV-style table. Columns: date, row_count, freshness_s, + up to 3 null_rates
    from columns mentioned in fired checks.
    Last row gets ← ANOMALY marker if it's the incident profile.
    """
    if not profiles:
        return "  (no history)"

    # Pick which null_rate columns to show (fired checks first)
    sample_metrics = profiles[-1].column_metrics or {} if profiles else {}
    priority_cols = [
        col for col in sample_metrics.keys()
        if any(col in name for name in fired_check_names)
    ]
    other_cols = [c for c in sample_metrics.keys() if c not in priority_cols]
    show_cols = (priority_cols + other_cols)[:MAX_METRICS_PER_COL]

    col_headers = ["date", "rows", "freshness_s"] + [f"null_{c}" for c in show_cols]
    lines = ["  " + "\t".join(col_headers)]

    for i, p in enumerate(profiles):
        is_last = i == len(profiles) - 1
        dt = p.collected_at.strftime("%Y-%m-%d")
        row_count = str(p.row_count) if p.row_count is not None else "?"
        freshness = f"{p.freshness_seconds:.0f}" if p.freshness_seconds else "?"
        null_vals = []
        for col in show_cols:
            m = (p.column_metrics or {}).get(col, {})
            nr = m.get("null_rate") if isinstance(m, dict) else None
            null_vals.append(f"{nr:.3f}" if nr is not None else "?")
        row = "\t".join([dt, row_count, freshness] + null_vals)
        if is_last and any(name in fired_check_names for name in ["row_count_zero", "freshness_sla_breach"]):
            row += "\t← ANOMALY"
        lines.append("  " + row)

    return "\n".join(lines)


async def build_context(incident_id: str) -> str:
    """
    Assemble incident context as a compact human-readable string.
    Returns the full user message to send to the LLM.
    """
    from app.database import AsyncSessionLocal
    from app.models.data_source import DataSource
    from app.models.incident import Incident
    from app.models.monitored_table import MonitoredTable
    from app.models.table_profile import TableProfile

    async with AsyncSessionLocal() as db:
        incident = await db.get(Incident, incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        table = await db.get(MonitoredTable, incident.table_id)
        source = await db.get(DataSource, table.source_id)

        # Last 14 profiles (excluding errors)
        history = (await db.scalars(
            select(TableProfile)
            .where(TableProfile.table_id == table.id, TableProfile.error.is_(None))
            .order_by(desc(TableProfile.collected_at))
            .limit(HISTORY_DAYS)
        )).all()
        history = list(reversed(history))

    fired_check_names = {c.get("check_name", "") for c in (incident.fired_checks or [])}

    # Build compact context string
    lines = [
        "=== INCIDENT ===",
        f"ID:        {incident.id}",
        f"Severity:  {incident.severity}",
        f"Title:     {incident.title}",
        f"Detected:  {incident.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "=== SOURCE ===",
        f"Warehouse: {source.name} ({source.type})",
        f"Table:     {table.schema_name}.{table.table_name}",
        f"Freshness column: {table.freshness_column or 'none'}",
        f"Check interval:   {table.check_interval_minutes} minutes",
        f"Sensitivity:      {table.sensitivity}σ",
        "",
        "=== FAILED CHECKS ===",
        _format_checks(incident.fired_checks or []),
        "",
        "=== PROFILE HISTORY (last 14 days) ===",
        _format_profile_history(history, fired_check_names),
    ]

    if table.dbt_model_yaml:
        lines += ["", "=== DBT MODEL ===", table.dbt_model_yaml[:1000]]

    return "\n".join(lines)
