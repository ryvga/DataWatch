"""Custom SQL monitors — per-table user-defined checks."""
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.factory import ConnectorFactory
from app.database import get_db
from app.models.check_result import CheckResult
from app.models.custom_monitor import CustomMonitor
from app.models.data_source import DataSource
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.routers.auth import get_current_org_from_jwt
from app.services.anomaly import AnomalyResult
from app.services.crypto import decrypt_config
from app.services.incident import IncidentService
from app.services.legacy_sql_monitor import (
    LegacySqlPolicyError,
    LegacySqlResultError,
    execute_legacy_monitor,
    validate_legacy_sql,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tables", tags=["custom_monitors"])
org_router = APIRouter(prefix="/api/v1", tags=["custom_monitors"])

_SQL_WHITESPACE_RE = re.compile(r"\s+")


def _canonical_sql(sql: str) -> str:
    return _SQL_WHITESPACE_RE.sub(" ", sql.strip()).lower()


async def _ensure_unique_active_sql(
    table_id: str,
    org_id,
    sql_query: str,
    db: AsyncSession,
    *,
    exclude_monitor_id: str | None = None,
) -> None:
    target = _canonical_sql(sql_query)
    monitors = (await db.scalars(
        select(CustomMonitor).where(
            CustomMonitor.table_id == table_id,
            CustomMonitor.org_id == org_id,
            CustomMonitor.is_active == True,
        )
    )).all()
    for monitor in monitors:
        if exclude_monitor_id and str(monitor.id) == str(exclude_monitor_id):
            continue
        if _canonical_sql(monitor.sql_query) == target:
            raise HTTPException(
                status_code=409,
                detail=f'A custom monitor with this SQL already exists for this table: "{monitor.name}".',
            )


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


async def _get_source_or_404(
    table: MonitoredTable, org: Organization, db: AsyncSession
) -> DataSource:
    source = await db.scalar(
        select(DataSource).where(
            DataSource.id == table.source_id,
            DataSource.org_id == org.id,
        )
    )
    if not source:
        raise HTTPException(status_code=404, detail="Table not found")
    return source


def _validate_monitor_sql(
    sql: str,
    severity: str,
    *,
    source: DataSource,
    table: MonitoredTable,
) -> str:
    capability = ConnectorFactory.capabilities_for(source.type)["custom_monitors"]
    if capability != "legacy_sql_scalar":
        raise HTTPException(
            status_code=422,
            detail=f"{source.type} has no restricted custom monitor execution path",
        )
    try:
        return validate_legacy_sql(
            sql,
            severity,
            source_type=source.type,
            target_schema=table.schema_name,
            target_table=table.table_name,
        )
    except LegacySqlPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _record_run_error(
    monitor: CustomMonitor, db: AsyncSession, error: Exception
) -> None:
    now = datetime.now(timezone.utc)
    monitor.last_run_at = now
    monitor.last_result = {"error": str(error), "executed_at": now.isoformat()}
    await db.commit()


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
    table = await _get_table_or_404(table_id, org, db)
    source = await _get_source_or_404(table, org, db)
    query = _validate_monitor_sql(
        body.sql_query,
        body.severity,
        source=source,
        table=table,
    )
    await _ensure_unique_active_sql(table_id, org.id, body.sql_query, db)

    monitor = CustomMonitor(
        table_id=table_id,
        org_id=org.id,
        name=body.name,
        description=body.description,
        sql_query=query,
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
    table = await _get_table_or_404(table_id, org, db)
    source = await _get_source_or_404(table, org, db)
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
        update["sql_query"] = _validate_monitor_sql(
            update.get("sql_query", monitor.sql_query),
            update.get("severity", monitor.severity),
            source=source,
            table=table,
        )
    next_active = update.get("is_active", monitor.is_active)
    if next_active:
        await _ensure_unique_active_sql(
            table_id,
            org.id,
            update.get("sql_query", monitor.sql_query),
            db,
            exclude_monitor_id=monitor_id,
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
    if not monitor.is_active:
        raise HTTPException(status_code=409, detail="Custom monitor is inactive")

    src = await _get_source_or_404(table, org, db)

    try:
        query = _validate_monitor_sql(
            monitor.sql_query,
            monitor.severity,
            source=src,
            table=table,
        )
        config = decrypt_config(src.connection_config["encrypted"], str(org.id))
        connector = ConnectorFactory.create(src.type, config)
        try:
            _, violation_count = await execute_legacy_monitor(connector, query)
        finally:
            await connector.close()

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
    except (LegacySqlPolicyError, LegacySqlResultError) as e:
        logger.warning("Custom monitor policy/result error: %s", e)
        await _record_run_error(monitor, db, e)
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.warning("Custom monitor run failed: %s", e)
        await _record_run_error(monitor, db, e)
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
