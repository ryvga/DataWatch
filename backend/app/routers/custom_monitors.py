"""Custom SQL monitors — per-table user-defined checks."""
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.check_result import CheckResult
from app.models.custom_monitor import CustomMonitor
from app.models.data_source import DataSource
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.routers.auth import get_current_org_from_jwt
from app.routers.tables import _violation_count_from_result
from app.services.anomaly import AnomalyResult
from app.services.crypto import decrypt_config
from app.services.incident import IncidentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tables", tags=["custom_monitors"])
org_router = APIRouter(prefix="/api/v1", tags=["custom_monitors"])

# ── SQL safety ────────────────────────────────────────────────────────────────

_BLOCKED_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "GRANT", "TRUNCATE")
_BLOCKED_RE = re.compile(r"\b(" + "|".join(_BLOCKED_KEYWORDS) + r")\b", re.IGNORECASE)
_SEVERITIES = {"P1", "P2", "P3"}


def _strip_quoted(sql: str) -> str:
    out, quote, i = [], None, 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == quote and i + 1 < len(sql) and sql[i + 1] == quote:
                out.extend("  "); i += 2; continue
            if ch == quote:
                quote = None
            out.append(" ")
        else:
            if ch in {"'", '"', "`"}:
                quote = ch; out.append(" ")
            else:
                out.append(ch)
        i += 1
    return "".join(out)


def _validate_sql(sql: str, severity: str) -> None:
    s = sql.strip()
    if not re.match(r"^SELECT\b", s, re.IGNORECASE):
        raise HTTPException(status_code=422, detail="SQL must start with SELECT")
    if severity not in _SEVERITIES:
        raise HTTPException(status_code=422, detail="Severity must be P1, P2, or P3")
    clean = _strip_quoted(s)
    if ";" in clean:
        raise HTTPException(status_code=422, detail="SQL must not contain semicolons")
    m = _BLOCKED_RE.search(clean)
    if m:
        raise HTTPException(status_code=422, detail=f"SQL contains prohibited keyword: {m.group(1).upper()}")


# ── Schemas ───────────────────────────────────────────────────────────────────

class CustomMonitorCreate(BaseModel):
    name: str
    description: str | None = None
    sql_query: str
    severity: str = "P3"
    run_on_profile: bool = True


class CustomMonitorUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    sql_query: str | None = None
    severity: str | None = None
    is_active: bool | None = None
    run_on_profile: bool | None = None


class CustomMonitorResponse(BaseModel):
    id: str
    table_id: str
    name: str
    description: str | None
    sql_query: str
    severity: str
    is_active: bool
    run_on_profile: bool
    created_at: datetime
    last_run_at: datetime | None
    last_result: dict | None


class RunResult(BaseModel):
    violation_count: int
    passed: bool
    executed_at: datetime
    error: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_response(m: CustomMonitor) -> CustomMonitorResponse:
    return CustomMonitorResponse(
        id=str(m.id),
        table_id=str(m.table_id),
        name=m.name,
        description=m.description,
        sql_query=m.sql_query,
        severity=m.severity,
        is_active=m.is_active,
        run_on_profile=m.run_on_profile,
        created_at=m.created_at,
        last_run_at=m.last_run_at,
        last_result=m.last_result,
    )


async def _get_table_or_404(table_id: str, org: Organization, db: AsyncSession) -> MonitoredTable:
    table = await db.scalar(select(MonitoredTable).where(MonitoredTable.id == table_id))
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    src = await db.scalar(
        select(DataSource).where(DataSource.id == table.source_id, DataSource.org_id == org.id)
    )
    if not src:
        raise HTTPException(status_code=404, detail="Table not found")
    return table


async def _get_monitor_or_404(monitor_id: str, table_id: str, org_id) -> CustomMonitor:
    raise HTTPException(status_code=404, detail="Monitor not found")


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("/{table_id}/custom-monitors", response_model=list[CustomMonitorResponse])
async def list_custom_monitors(
    table_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    await _get_table_or_404(table_id, org, db)
    monitors = (await db.scalars(
        select(CustomMonitor)
        .where(CustomMonitor.table_id == table_id, CustomMonitor.org_id == org.id)
        .order_by(desc(CustomMonitor.created_at))
    )).all()
    return [_to_response(m) for m in monitors]


@router.post("/{table_id}/custom-monitors", response_model=CustomMonitorResponse, status_code=201)
async def create_custom_monitor(
    table_id: str,
    body: CustomMonitorCreate,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    await _get_table_or_404(table_id, org, db)
    _validate_sql(body.sql_query, body.severity)

    monitor = CustomMonitor(
        table_id=table_id,
        org_id=org.id,
        name=body.name,
        description=body.description,
        sql_query=body.sql_query,
        severity=body.severity,
        is_active=True,
        run_on_profile=body.run_on_profile,
    )
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)
    return _to_response(monitor)


@router.patch("/{table_id}/custom-monitors/{monitor_id}", response_model=CustomMonitorResponse)
async def update_custom_monitor(
    table_id: str,
    monitor_id: str,
    body: CustomMonitorUpdate,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    await _get_table_or_404(table_id, org, db)
    monitor = await db.scalar(
        select(CustomMonitor).where(
            CustomMonitor.id == monitor_id,
            CustomMonitor.table_id == table_id,
            CustomMonitor.org_id == org.id,
        )
    )
    if not monitor:
        raise HTTPException(status_code=404, detail="Custom monitor not found")

    update = body.model_dump(exclude_none=True)
    if "sql_query" in update or "severity" in update:
        _validate_sql(
            update.get("sql_query", monitor.sql_query),
            update.get("severity", monitor.severity),
        )
    for field, value in update.items():
        setattr(monitor, field, value)

    await db.commit()
    await db.refresh(monitor)
    return _to_response(monitor)


@router.delete("/{table_id}/custom-monitors/{monitor_id}", status_code=204)
async def delete_custom_monitor(
    table_id: str,
    monitor_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    await _get_table_or_404(table_id, org, db)
    monitor = await db.scalar(
        select(CustomMonitor).where(
            CustomMonitor.id == monitor_id,
            CustomMonitor.table_id == table_id,
            CustomMonitor.org_id == org.id,
        )
    )
    if not monitor:
        raise HTTPException(status_code=404, detail="Custom monitor not found")
    await db.delete(monitor)
    await db.commit()


# ── Run endpoint ──────────────────────────────────────────────────────────────

@router.post("/{table_id}/custom-monitors/{monitor_id}/run", response_model=RunResult)
async def run_custom_monitor(
    table_id: str,
    monitor_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    monitor = await db.scalar(
        select(CustomMonitor).where(
            CustomMonitor.id == monitor_id,
            CustomMonitor.table_id == table_id,
            CustomMonitor.org_id == org.id,
        )
    )
    if not monitor:
        raise HTTPException(status_code=404, detail="Custom monitor not found")

    src = await db.scalar(
        select(DataSource).where(DataSource.id == table.source_id, DataSource.org_id == org.id)
    )

    try:
        config = decrypt_config(src.connection_config["encrypted"], str(org.id))
        from app.connectors.factory import ConnectorFactory
        connector = ConnectorFactory.create(src.type, config)
        try:
            result = await connector.execute_profile_query(monitor.sql_query.strip())
        finally:
            await connector.close()

        violation_count = _violation_count_from_result(result)
        passed = violation_count == 0
        now = datetime.now(timezone.utc)

        monitor.last_run_at = now
        monitor.last_result = {
            "violation_count": violation_count,
            "passed": passed,
            "executed_at": now.isoformat(),
        }
        check = AnomalyResult(
            check_type="custom_sql",
            check_name=f"custom_monitor:{monitor.name}",
            column_name=None,
            status="passed" if passed else "failed",
            observed_value=float(violation_count),
            expected_range={"low": 0, "high": 0},
            deviation_score=float(violation_count),
            details={"monitor_id": str(monitor.id), "severity": monitor.severity},
        )
        db.add(CheckResult(
            table_id=table.id,
            profile_id=None,
            check_type=check.check_type,
            check_name=check.check_name,
            column_name=check.column_name,
            status=check.status,
            observed_value=check.observed_value,
            expected_range=check.expected_range,
            deviation_score=check.deviation_score,
        ))

        svc = IncidentService()
        if passed:
            await svc.auto_resolve(db, table, [check])
        else:
            incident = await svc.create_or_update(db, org.id, table, [check], None)
            if incident and incident.status == "open":
                from app.tasks import generate_llm_narration
                generate_llm_narration.delay(str(incident.id))

        await db.commit()

        return RunResult(violation_count=violation_count, passed=passed, executed_at=now)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Custom monitor run failed: %s", e)
        raise HTTPException(status_code=422, detail=f"Custom monitor run failed: {e}") from e


# ── Org-wide endpoint ─────────────────────────────────────────────────────────

@org_router.get("/custom-monitors", response_model=list[CustomMonitorResponse])
async def list_all_custom_monitors(
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """All custom monitors across all tables for this org — single call."""
    monitors = (await db.scalars(
        select(CustomMonitor)
        .where(CustomMonitor.org_id == org.id)
        .order_by(desc(CustomMonitor.created_at))
    )).all()
    return [_to_response(m) for m in monitors]
