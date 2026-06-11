"""First-table onboarding automation for monitor recommendations."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.services.crypto import CryptoService
from app.services.monitor_recommender import recommend_monitors

logger = logging.getLogger(__name__)


def initial_autopilot_state() -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "status": "queued",
        "started_at": now,
        "updated_at": now,
        "recommended_next_action": "Profiling and AI monitor recommendations are queued.",
        "steps": {
            "profile": {"status": "queued", "label": "First profile"},
            "safe_baseline": {"status": "pending", "label": "Safe baseline monitors"},
            "recommendations": {"status": "queued", "label": "AI monitor recommendations", "staged_count": 0},
            "alerts": {"status": "pending", "label": "Alert routing"},
        },
        "safe_monitors": [],
        "recommendations": [],
        "messages": [],
    }


def not_started_autopilot_state() -> dict:
    return {
        "status": "not_started",
        "recommended_next_action": "Run a profile or add a new table to start monitor autopilot.",
        "steps": {
            "profile": {"status": "needs_run", "label": "First profile"},
            "safe_baseline": {"status": "pending", "label": "Safe baseline monitors"},
            "recommendations": {"status": "pending", "label": "AI monitor recommendations", "staged_count": 0},
            "alerts": {"status": "pending", "label": "Alert routing"},
        },
        "safe_monitors": [],
        "recommendations": [],
        "messages": [],
    }


def mark_profile_step(state: dict | None, *, status: str, profile_id: str | None = None, error: str | None = None) -> dict:
    state = dict(state or initial_autopilot_state())
    steps = dict(state.get("steps") or {})
    profile = dict(steps.get("profile") or {})
    profile["status"] = status
    if profile_id:
        profile["profile_id"] = profile_id
    if error:
        profile["error"] = error
    steps["profile"] = profile
    state["steps"] = steps
    state["updated_at"] = datetime.now(UTC).isoformat()
    if status == "complete" and state.get("status") == "queued":
        state["status"] = "profiling_complete"
        state["recommended_next_action"] = "Review staged AI monitor recommendations."
    return state


_DDL_COLUMN_RE = re.compile(
    r"^\s*\"?`?(?P<name>[A-Za-z_][\w$]*)\"?`?\s+(?P<type>[A-Za-z][\w\s()]+?)(?:\s+|,|$)(?P<nullable>NOT NULL|NULL)?",
    re.IGNORECASE,
)


def columns_from_ddl(ddl: str | None) -> list[dict]:
    if not ddl:
        return []
    columns: list[dict] = []
    for raw in ddl.splitlines():
        line = raw.strip().rstrip(",")
        if not line or line.upper().startswith(("CREATE ", ");", ")")):
            continue
        match = _DDL_COLUMN_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        dtype = " ".join(match.group("type").split()).lower()
        nullable_token = (match.group("nullable") or "").upper()
        category = _category_for_type(dtype, name)
        columns.append(
            {
                "name": name,
                "data_type": dtype,
                "category": category,
                "nullable": nullable_token != "NOT NULL",
            }
        )
    return columns


def _category_for_type(dtype: str, name: str) -> str:
    text = f"{dtype} {name}".lower()
    if any(token in text for token in ("timestamp", "datetime", "timestamptz", "created_at", "updated_at", "loaded_at")):
        return "timestamp"
    if re.search(r"\bdate\b", text):
        return "date"
    if any(token in dtype for token in ("int", "numeric", "decimal", "double", "float", "real")):
        return "numeric"
    if "bool" in dtype:
        return "boolean"
    return "text"


def _is_safe_builtin(monitor: dict) -> bool:
    return monitor.get("monitor_type") in {
        "freshness",
        "row_count",
        "null_rate",
        "duplicate",
        "schema_drift",
        "value_range",
        "enum_drift",
    }


def _staged_monitor(monitor: dict, index: int) -> dict:
    return {
        "id": f"rec_{index + 1}",
        "status": "staged",
        "requires_review": True,
        "monitor_type": monitor.get("monitor_type", "custom_sql"),
        "name": monitor.get("name") or f"Recommended monitor {index + 1}",
        "column_name": monitor.get("column_name"),
        "rationale": monitor.get("rationale") or "",
        "severity": monitor.get("severity") or "P3",
        "config": monitor.get("config") if isinstance(monitor.get("config"), dict) else {},
    }


async def run_table_autopilot(db: AsyncSession, table: MonitoredTable, source: DataSource, org: Organization) -> dict:
    from sqlalchemy import select
    from app.models.custom_monitor import CustomMonitor

    state = dict(table.autopilot or initial_autopilot_state())
    steps = dict(state.get("steps") or {})
    messages = list(state.get("messages") or [])

    columns = columns_from_ddl(table.dbt_model_yaml)
    org_api_key = None
    if org.llm_api_key_encrypted:
        try:
            org_api_key = CryptoService().decrypt_for_org(org.llm_api_key_encrypted, str(org.id))
        except Exception:
            messages.append({"level": "warning", "text": "Organization LLM key could not be decrypted; using global fallback if configured."})

    # Collect already-active monitors to avoid duplicates in recommendations
    existing_custom = (await db.scalars(
        select(CustomMonitor).where(CustomMonitor.table_id == table.id, CustomMonitor.is_active == True)
    )).all()
    existing_monitors: list[dict] = [
        {"monitor_type": "custom_sql", "name": m.name, "column_name": None}
        for m in existing_custom
    ]
    prior_safe = list(state.get("safe_monitors") or [])
    existing_monitors.extend(prior_safe)
    prior_recs = [r for r in (state.get("recommendations") or []) if r.get("status") == "applied"]
    existing_monitors.extend(prior_recs)

    try:
        recommendations = await recommend_monitors(
            table.table_name,
            columns,
            org_api_key,
            org.llm_model,
            db_type=source.type,
            existing_monitors=existing_monitors,
        )
    except Exception as exc:
        logger.warning("Autopilot recommendations failed for table %s: %s", table.id, exc)
        recommendations = []
        messages.append({"level": "warning", "text": "AI monitor recommendations failed; baseline checks remain active."})

    safe_monitors: list[dict[str, Any]] = []
    staged: list[dict[str, Any]] = []
    for idx, monitor in enumerate(recommendations):
        if _is_safe_builtin(monitor):
            safe_monitors.append({**monitor, "status": "enabled", "requires_review": False})
            if monitor.get("monitor_type") == "freshness" and monitor.get("column_name") and not table.freshness_column:
                table.freshness_column = monitor["column_name"]
        else:
            staged.append(_staged_monitor(monitor, idx))

    if not safe_monitors:
        safe_monitors.append(
            {
                "monitor_type": "row_count",
                "name": f"{table.table_name} row count baseline",
                "rationale": "Panopta always checks for empty tables and anomalous row-count shifts after profiling.",
                "severity": "P1",
                "status": "enabled",
                "requires_review": False,
                "config": {"built_in": True},
            }
        )

    steps["safe_baseline"] = {
        "status": "enabled",
        "label": "Safe baseline monitors",
        "enabled_count": len(safe_monitors),
    }
    steps["recommendations"] = {
        "status": "ready",
        "label": "AI monitor recommendations",
        "staged_count": len(staged),
    }
    steps["alerts"] = {
        "status": "needs_review",
        "label": "Alert routing",
        "message": "Choose where P1/P2 incidents should be sent.",
    }

    state.update(
        {
            "status": "ready",
            "updated_at": datetime.now(UTC).isoformat(),
            "recommended_next_action": (
                f"Review {len(staged)} staged AI monitor recommendation(s)."
                if staged
                else "Baseline monitoring is active. Configure alert routing next."
            ),
            "steps": steps,
            "safe_monitors": safe_monitors,
            "recommendations": staged,
            "messages": messages,
        }
    )
    table.autopilot = state
    return state
