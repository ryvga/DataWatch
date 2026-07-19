import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import ConnectorConfigurationError
from app.connectors.factory import ConnectorFactory
from app.database import get_db
from app.models.check_result import CheckResult
from app.models.data_source import DataSource
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.models.table_profile import TableProfile
from app.routers.auth import get_current_org_from_jwt
from app.services.crypto import decrypt_config
from app.services.legacy_sql_monitor import (
    LegacySqlPolicyError,
    LegacySqlResultError,
    execute_legacy_monitor,
    validate_legacy_sql,
)
from app.services.schema_binding import parse_ddl_columns
from app.services.table_autopilot import initial_autopilot_state, not_started_autopilot_state

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
    owner_team_id: str | None = None
    owner_user_id: str | None = None
    check_config: dict | None = None


class ProfileSummary(BaseModel):
    id: str
    collected_at: datetime
    row_count: int | None
    freshness_seconds: float | None
    schema_fingerprint: str | None
    profiling_duration_ms: int | None
    error: str | None
    column_metrics: dict | None = None  # only populated on latest_profile, not in list
    profile_provenance: dict | None = None


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
    autopilot: dict | None = None
    check_config: dict | None = None


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
        profile_provenance=getattr(p, "profile_provenance", None),
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
        autopilot=table.autopilot or not_started_autopilot_state(),
        check_config=table.check_config,
    )


async def _verified_schema_snapshot(
    source: DataSource,
    org_id: str,
    schema_name: str,
    table_name: str,
    freshness_column: str | None,
) -> tuple[str, set[str]]:
    """Fetch the server-owned DDL snapshot used to bind monitors and freshness."""
    connector = None
    native_column_names = None
    try:
        config = decrypt_config(source.connection_config["encrypted"], org_id)
        connector = ConnectorFactory.create(source.type, config)
        get_table_schema = getattr(connector, "get_table_schema", None)
        if callable(get_table_schema):
            snapshot, native_column_names = await get_table_schema(
                schema_name,
                table_name,
            )
        else:
            snapshot = await connector.get_table_ddl(schema_name, table_name)
        validate_profile_config = getattr(connector, "validate_profile_config", None)
        if callable(validate_profile_config):
            await validate_profile_config(
                schema_name,
                table_name,
                freshness_column,
            )
    except ConnectorConfigurationError as e:
        logger.warning("Table profile configuration rejected: %s", type(e).__name__)
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.warning("Table schema snapshot failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not verify the table schema. Confirm the schema/table name "
                "and source connectivity."
            ),
        ) from e
    finally:
        if connector is not None:
            try:
                await connector.close()
            except Exception as e:
                logger.warning("Table schema connector close failed: %s", type(e).__name__)

    columns = parse_ddl_columns(snapshot) if native_column_names is None else ()
    column_names = (
        {column.name for column in columns}
        if native_column_names is None
        else set(native_column_names)
    )
    is_native_profile = bool(
        connector is not None and getattr(connector, "native_profile_kind", None)
    )
    if freshness_column and is_native_profile:
        column_names.add(freshness_column)
    if not column_names and not is_native_profile:
        raise HTTPException(
            status_code=422,
            detail="The connector did not return a structured schema with any columns.",
        )
    return snapshot, column_names


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=TableResponse, status_code=201)
async def create_table(
    body: TableCreate,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    source = await _resolve_org_from_source(body.source_id, org, db)
    profile_capability = ConnectorFactory.capabilities_for(source.type)["profiling"]
    if profile_capability == "none":
        raise HTTPException(
            status_code=422,
            detail=(
                f"{source.type} supports connection/discovery but not scheduled profiling yet"
            ),
        )

    # Reject duplicate (same source + schema + table)
    existing = await db.scalar(
        select(MonitoredTable).where(
            MonitoredTable.source_id == body.source_id,
            MonitoredTable.schema_name == body.schema_name,
            MonitoredTable.table_name == body.table_name,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Table {body.schema_name}.{body.table_name} is already monitored for this source.")

    # Enforce plan limit
    from app.services.plans import enforce_table_limit
    await enforce_table_limit(org, db)

    if body.dbt_model_yaml is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "dbt_model_yaml is no longer accepted during onboarding; "
                "schema snapshots are captured from the source."
            ),
        )

    schema_snapshot, column_names = await _verified_schema_snapshot(
        source,
        str(org.id),
        body.schema_name,
        body.table_name,
        body.freshness_column,
    )
    if body.freshness_column and body.freshness_column not in column_names:
        raise HTTPException(
            status_code=422,
            detail="freshness_column must exist in the verified table schema.",
        )

    table = MonitoredTable(
        source_id=body.source_id,
        schema_name=body.schema_name,
        table_name=body.table_name,
        freshness_column=body.freshness_column,
        check_interval_minutes=body.check_interval_minutes,
        sensitivity=body.sensitivity,
        dbt_model_yaml=schema_snapshot,
        autopilot=initial_autopilot_state(),
        is_active=True,
    )
    db.add(table)
    await db.flush()

    # Enqueue first profile run
    from app.tasks import profile_table
    profile_table.delay(str(table.id))

    # Enqueue AI onboarding/recommendation workflow. It is intentionally
    # separate from profiling so a slow LLM call never blocks table creation.
    from app.tasks import bootstrap_table_autopilot
    bootstrap_table_autopilot.delay(str(table.id))

    # Register scheduler job
    from app.scheduler import add_table_job
    add_table_job(str(table.id), table.check_interval_minutes)

    return _table_response(table)


@router.get("", response_model=list[TableResponse])
async def list_tables(
    owner_team_id: str | None = Query(None),
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    # Get all sources for this org
    source_ids = (await db.scalars(
        select(DataSource.id).where(DataSource.org_id == org.id)
    )).all()

    q = select(MonitoredTable).where(MonitoredTable.source_id.in_(source_ids))
    if owner_team_id:
        q = q.where(MonitoredTable.owner_team_id == owner_team_id)

    tables = (await db.scalars(q)).all()

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
    update_data = body.model_dump(exclude_unset=True)
    if update_data.get("dbt_model_yaml") is not None:
        raise HTTPException(
            status_code=422,
            detail="dbt_model_yaml is read-only; schema snapshots are captured from the source.",
        )
    update_data.pop("dbt_model_yaml", None)

    freshness_column = update_data.get("freshness_column")
    if freshness_column is not None:
        source = await db.get(DataSource, table.source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")
        schema_snapshot, column_names = await _verified_schema_snapshot(
            source,
            str(org.id),
            table.schema_name,
            table.table_name,
            freshness_column,
        )
        if freshness_column not in column_names:
            raise HTTPException(
                status_code=422,
                detail="freshness_column must exist in the verified table schema.",
            )
        table.dbt_model_yaml = schema_snapshot

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


@router.post("/{table_id}/retry-autopilot", status_code=202)
async def retry_autopilot(
    table_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await _get_table_or_404(table_id, org, db)
    from app.services.table_autopilot import initial_autopilot_state
    table.autopilot = initial_autopilot_state()
    await db.commit()
    from app.tasks import bootstrap_table_autopilot
    task = bootstrap_table_autopilot.delay(str(table.id))
    return {"status": "queued", "task_id": str(task.id)}


@router.post("/{table_id}/custom-check", response_model=CustomCheckResponse)
async def run_custom_check(
    table_id: str,
    body: CustomCheckRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    try:
        table = await _get_table_or_404(table_id, org, db)
        source = await db.scalar(
            select(DataSource).where(DataSource.id == table.source_id, DataSource.org_id == org.id)
        )
        if not source:
            raise HTTPException(status_code=422, detail="Table data source not found")
        if (
            ConnectorFactory.capabilities_for(source.type)["custom_monitors"]
            != "legacy_sql_scalar"
        ):
            raise HTTPException(
                status_code=422,
                detail=f"{source.type} has no restricted custom monitor execution path",
            )

        query = validate_legacy_sql(
            body.sql,
            body.severity,
            source_type=source.type,
            target_schema=table.schema_name,
            target_table=table.table_name,
        )

        config = decrypt_config(source.connection_config["encrypted"], str(org.id))
        connector = ConnectorFactory.create(source.type, config)
        try:
            result, violation_count = await execute_legacy_monitor(connector, query)
        finally:
            await connector.close()

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
    except (LegacySqlPolicyError, LegacySqlResultError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
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
            profile_provenance=getattr(p, "profile_provenance", None),
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
        "profile_provenance": getattr(p, "profile_provenance", None),
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
