import logging
import re
from datetime import datetime, timezone
from numbers import Number

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.factory import ConnectorFactory
from app.database import get_db
from app.models.check_result import CheckResult
from app.models.data_source import DataSource
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.models.table_profile import TableProfile
from app.routers.auth import get_current_org_from_jwt
from app.services.crypto import decrypt_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tables", tags=["tables"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class TableCreate(BaseModel):
    source_id: str
    schema_name: str
    table_name: str
    freshness_column: str | None = None
    check_interval_minutes: int = 60
    sensitivity: float = 3.0
    dbt_model_yaml: str | None = None


class TableUpdate(BaseModel):
    freshness_column: str | None = None
    check_interval_minutes: int | None = None
    sensitivity: float | None = None
    dbt_model_yaml: str | None = None
    is_active: bool | None = None


class ProfileSummary(BaseModel):
    id: str
    collected_at: datetime
    row_count: int | None
    freshness_seconds: float | None
    schema_fingerprint: str | None
    profiling_duration_ms: int | None
    error: str | None
    column_metrics: dict | None = None  # only populated on latest_profile, not in list


class TableResponse(BaseModel):
    id: str
    source_id: str
    schema_name: str
    table_name: str
    freshness_column: str | None
    check_interval_minutes: int
    sensitivity: float
    is_active: bool
    last_profiled_at: datetime | None
    schema_snapshot: str | None = None
    latest_profile: ProfileSummary | None = None


class RunResponse(BaseModel):
    task_id: str
    queued_at: datetime


class CheckResultResponse(BaseModel):
    id: str
    profile_id: str | None
    check_type: str
    check_name: str
    column_name: str | None
    status: str
    observed_value: float | None
    expected_range: dict | None
    deviation_score: float | None
    checked_at: datetime


class CustomCheckRequest(BaseModel):
    sql: str
    name: str
    severity: str = "P3"


class CustomCheckResponse(BaseModel):
    result: dict
    violation_count: int
    passed: bool
    executed_at: datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

_BLOCKED_SQL_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "CREATE",
    "ALTER",
    "GRANT",
    "TRUNCATE",
)
_BLOCKED_SQL_RE = re.compile(
    r"\b(" + "|".join(_BLOCKED_SQL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def _sql_without_quoted_content(sql: str) -> str:
    chars: list[str] = []
    quote: str | None = None
    i = 0

    while i < len(sql):
        ch = sql[i]
        if quote:
            if ch == quote:
                next_ch = sql[i + 1] if i + 1 < len(sql) else ""
                if next_ch == quote:
                    chars.extend("  ")
                    i += 2
                    continue
                quote = None
            chars.append(" ")
            i += 1
            continue

        if ch in {"'", '"', "`"}:
            quote = ch
            chars.append(" ")
        else:
            chars.append(ch)
        i += 1

    return "".join(chars)


def _validate_custom_check_sql(sql: str, severity: str) -> None:
    stripped = sql.strip()
    if not re.match(r"^SELECT\b", stripped, re.IGNORECASE):
        raise HTTPException(status_code=422, detail="SQL must start with SELECT")

    if severity not in {"P1", "P2", "P3"}:
        raise HTTPException(status_code=422, detail="Severity must be one of P1, P2, or P3")

    sql_for_checks = _sql_without_quoted_content(stripped)
    if ";" in sql_for_checks:
        raise HTTPException(status_code=422, detail="SQL must not contain semicolons")

    blocked_match = _BLOCKED_SQL_RE.search(sql_for_checks)
    if blocked_match:
        keyword = blocked_match.group(1).upper()
        raise HTTPException(status_code=422, detail=f"SQL contains prohibited keyword: {keyword}")


def _violation_count_from_result(result: dict) -> int:
    if not result:
        return 0

    first_value = next(iter(result.values()))
    if isinstance(first_value, Number) and not isinstance(first_value, bool):
        return int(first_value)
    return 0


async def _resolve_org_from_source(source_id: str, org: Organization, db: AsyncSession) -> DataSource:
    src = await db.scalar(
        select(DataSource).where(DataSource.id == source_id, DataSource.org_id == org.id)
    )
    if not src:
        raise HTTPException(status_code=404, detail="Data source not found")
    return src


async def _get_table_or_404(table_id: str, org: Organization, db: AsyncSession) -> MonitoredTable:
    """Load table and verify it belongs to this org via source."""
    table = await db.scalar(select(MonitoredTable).where(MonitoredTable.id == table_id))
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    # Verify org ownership via source
    source = await db.scalar(
        select(DataSource).where(DataSource.id == table.source_id, DataSource.org_id == org.id)
    )
    if not source:
        raise HTTPException(status_code=404, detail="Table not found")
    return table


async def _latest_profile(table_id, db: AsyncSession) -> ProfileSummary | None:
    p = await db.scalar(
        select(TableProfile)
        .where(TableProfile.table_id == table_id)
        .order_by(desc(TableProfile.collected_at))
        .limit(1)
    )
    if not p:
        return None
    return ProfileSummary(
        id=str(p.id),
        collected_at=p.collected_at,
        row_count=p.row_count,
        freshness_seconds=p.freshness_seconds,
        schema_fingerprint=p.schema_fingerprint,
        profiling_duration_ms=p.profiling_duration_ms,
        error=p.error,
        column_metrics=p.column_metrics,
    )


def _table_response(table: MonitoredTable, profile: ProfileSummary | None = None) -> TableResponse:
    return TableResponse(
        id=str(table.id),
        source_id=str(table.source_id),
        schema_name=table.schema_name,
        table_name=table.table_name,
        freshness_column=table.freshness_column,
        check_interval_minutes=table.check_interval_minutes,
        sensitivity=table.sensitivity,
        is_active=table.is_active,
        last_profiled_at=table.last_profiled_at,
        schema_snapshot=table.dbt_model_yaml,
        latest_profile=profile,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=TableResponse, status_code=201)
async def create_table(
    body: TableCreate,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    source = await _resolve_org_from_source(body.source_id, org, db)

    # Enforce plan limit
    from app.services.plans import enforce_table_limit
    await enforce_table_limit(org, db)

    schema_snapshot = body.dbt_model_yaml
    if not schema_snapshot:
        try:
            config = decrypt_config(source.connection_config["encrypted"], str(org.id))
            connector = ConnectorFactory.create(source.type, config)
            try:
                schema_snapshot = await connector.get_table_ddl(body.schema_name, body.table_name)
            finally:
                await connector.close()
        except Exception as e:
            logger.warning("Table schema snapshot failed: %s", type(e).__name__)

    table = MonitoredTable(
        source_id=body.source_id,
        schema_name=body.schema_name,
        table_name=body.table_name,
        freshness_column=body.freshness_column,
        check_interval_minutes=body.check_interval_minutes,
        sensitivity=body.sensitivity,
        dbt_model_yaml=schema_snapshot,
        is_active=True,
    )
    db.add(table)
    await db.flush()

    # Enqueue first profile run
    from app.tasks import profile_table
    profile_table.delay(str(table.id))

    # Register scheduler job
    from app.scheduler import add_table_job
    add_table_job(str(table.id), table.check_interval_minutes)

    return _table_response(table)


@router.get("", response_model=list[TableResponse])
async def list_tables(
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    # Get all sources for this org
    source_ids = (await db.scalars(
        select(DataSource.id).where(DataSource.org_id == org.id)
    )).all()

    tables = (await db.scalars(
        select(MonitoredTable).where(MonitoredTable.source_id.in_(source_ids))
    )).all()

    result = []
    for t in tables:
        profile = await _latest_profile(t.id, db)
        result.append(_table_response(t, profile))
    return result


@router.get("/{table_id}", response_model=TableResponse)
async def get_table(
    table_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    profile = await _latest_profile(table.id, db)
    return _table_response(table, profile)


@router.patch("/{table_id}", response_model=TableResponse)
async def update_table(
    table_id: str,
    body: TableUpdate,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(table, field, value)

    # Reschedule if interval changed
    if "check_interval_minutes" in update_data:
        from app.scheduler import reschedule_table_job
        reschedule_table_job(str(table.id), table.check_interval_minutes)

    # Remove job if deactivated
    if update_data.get("is_active") is False:
        from app.scheduler import remove_table_job
        remove_table_job(str(table.id))

    profile = await _latest_profile(table.id, db)
    return _table_response(table, profile)


@router.delete("/{table_id}", status_code=204)
async def deactivate_table(
    table_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    table.is_active = False
    from app.scheduler import remove_table_job
    remove_table_job(table_id)


@router.post("/{table_id}/run", response_model=RunResponse)
async def trigger_run(
    table_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    from app.tasks import profile_table
    task = profile_table.delay(str(table.id))
    return RunResponse(task_id=task.id, queued_at=datetime.now(timezone.utc))


@router.post("/{table_id}/profile", status_code=202)
async def trigger_profile(
    table_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    from app.tasks import profile_table
    task = profile_table.delay(str(table.id))
    return {"status": "queued", "task_id": str(task.id)}


@router.post("/{table_id}/custom-check", response_model=CustomCheckResponse)
async def run_custom_check(
    table_id: str,
    body: CustomCheckRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    try:
        _validate_custom_check_sql(body.sql, body.severity)
        table = await _get_table_or_404(table_id, org, db)
        source = await db.scalar(
            select(DataSource).where(DataSource.id == table.source_id, DataSource.org_id == org.id)
        )
        if not source:
            raise HTTPException(status_code=422, detail="Table data source not found")

        config = decrypt_config(source.connection_config["encrypted"], str(org.id))
        connector = ConnectorFactory.create(source.type, config)
        try:
            result = await connector.execute_profile_query(body.sql.strip())
        finally:
            await connector.close()

        violation_count = _violation_count_from_result(result)
        return CustomCheckResponse(
            result=result,
            violation_count=violation_count,
            passed=violation_count == 0,
            executed_at=datetime.now(timezone.utc),
        )
    except HTTPException as e:
        if e.status_code == 422:
            raise
        raise HTTPException(status_code=422, detail=str(e.detail)) from e
    except Exception as e:
        logger.warning("Custom check failed: %s", type(e).__name__)
        raise HTTPException(status_code=422, detail=f"Custom check failed: {e}") from e


@router.get("/{table_id}/profiles", response_model=list[ProfileSummary])
async def list_profiles(
    table_id: str,
    limit: int = 50,
    cursor: str | None = None,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)

    query = (
        select(TableProfile)
        .where(TableProfile.table_id == table.id)
        .order_by(desc(TableProfile.collected_at))
        .limit(min(limit, 250))
    )
    if cursor:
        query = query.where(TableProfile.collected_at < cursor)

    profiles = (await db.scalars(query)).all()
    return [
        ProfileSummary(
            id=str(p.id),
            collected_at=p.collected_at,
            row_count=p.row_count,
            freshness_seconds=p.freshness_seconds,
            schema_fingerprint=p.schema_fingerprint,
            profiling_duration_ms=p.profiling_duration_ms,
            error=p.error,
        )
        for p in profiles
    ]


@router.get("/{table_id}/profiles/{profile_id}")
async def get_profile(
    table_id: str,
    profile_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    p = await db.scalar(
        select(TableProfile).where(
            TableProfile.id == profile_id, TableProfile.table_id == table.id
        )
    )
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")

    return {
        "id": str(p.id),
        "table_id": str(p.table_id),
        "collected_at": p.collected_at,
        "row_count": p.row_count,
        "freshness_seconds": p.freshness_seconds,
        "schema_fingerprint": p.schema_fingerprint,
        "column_metrics": p.column_metrics,
        "profiling_duration_ms": p.profiling_duration_ms,
        "error": p.error,
    }


@router.get("/{table_id}/checks", response_model=list[CheckResultResponse])
async def list_checks(
    table_id: str,
    limit: int = 100,
    cursor: str | None = None,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    q = (
        select(CheckResult)
        .where(CheckResult.table_id == table.id)
        .order_by(desc(CheckResult.checked_at))
        .limit(min(limit, 500))
    )
    if cursor:
        q = q.where(CheckResult.checked_at < cursor)

    checks = (await db.scalars(q)).all()
    return [
        CheckResultResponse(
            id=str(c.id),
            profile_id=str(c.profile_id) if c.profile_id else None,
            check_type=c.check_type,
            check_name=c.check_name,
            column_name=c.column_name,
            status=c.status,
            observed_value=c.observed_value,
            expected_range=c.expected_range,
            deviation_score=c.deviation_score,
            checked_at=c.checked_at,
        )
        for c in checks
    ]


@router.get("/{table_id}/check-history", response_model=list[CheckResultResponse])
async def get_check_history(
    table_id: str,
    limit: int = 50,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    checks = (await db.scalars(
        select(CheckResult)
        .where(CheckResult.table_id == table.id)
        .order_by(desc(CheckResult.checked_at))
        .limit(min(limit, 500))
    )).all()

    return [
        CheckResultResponse(
            id=str(c.id),
            profile_id=str(c.profile_id) if c.profile_id else None,
            check_type=c.check_type,
            check_name=c.check_name,
            column_name=c.column_name,
            status=c.status,
            observed_value=c.observed_value,
            expected_range=c.expected_range,
            deviation_score=c.deviation_score,
            checked_at=c.checked_at,
        )
        for c in checks
    ]
