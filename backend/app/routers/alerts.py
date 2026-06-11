from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert_config import AlertConfig
from app.models.data_source import DataSource
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.routers.auth import get_current_org_from_jwt
from app.services.alert_policy import (
    CHANNELS,
    channel_available,
    channel_upgrade_detail,
    channels_for_org,
    effective_alert_plan,
    mask_alert_config,
    validate_alert_config,
)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AlertConfigCreate(BaseModel):
    table_id: str | None = None     # None = org-wide
    channel: str                    # slack | email | pagerduty
    config: dict                    # channel-specific config


class AlertConfigResponse(BaseModel):
    id: str
    table_id: str | None
    channel: str
    config: dict
    is_active: bool
    scope: str
    min_severity: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resp(a: AlertConfig) -> AlertConfigResponse:
    return AlertConfigResponse(
        id=str(a.id),
        table_id=str(a.table_id) if a.table_id else None,
        channel=a.channel,
        config=mask_alert_config(a.channel, a.config),
        is_active=a.is_active,
        scope="table" if a.table_id else "workspace",
        min_severity=(a.config or {}).get("min_severity", "P3"),
    )


async def _get_config_or_404(config_id: str, org: Organization, db: AsyncSession) -> AlertConfig:
    cfg = await db.scalar(
        select(AlertConfig).where(AlertConfig.id == config_id, AlertConfig.org_id == org.id)
    )
    if not cfg:
        raise HTTPException(status_code=404, detail="Alert config not found")
    return cfg


async def _validate_table_scope(table_id: str | None, org: Organization, db: AsyncSession) -> None:
    if not table_id:
        return
    table = await db.scalar(select(MonitoredTable).where(MonitoredTable.id == table_id))
    if not table:
        raise HTTPException(status_code=404, detail="Monitored table not found for this alert route.")
    source = await db.scalar(
        select(DataSource).where(DataSource.id == table.source_id, DataSource.org_id == org.id)
    )
    if not source:
        raise HTTPException(status_code=404, detail="Monitored table not found for this workspace.")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=AlertConfigResponse, status_code=201)
async def create_alert_config(
    body: AlertConfigCreate,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    if body.channel not in CHANNELS:
        raise HTTPException(status_code=400, detail=f"Alert channel must be one of: {', '.join(CHANNELS)}.")
    if not channel_available(org.plan, org.subscription_status, body.channel):
        raise HTTPException(status_code=402, detail=channel_upgrade_detail(org.plan, org.subscription_status, body.channel))
    await _validate_table_scope(body.table_id, org, db)
    try:
        config = validate_alert_config(body.channel, body.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cfg = AlertConfig(
        org_id=org.id,
        table_id=body.table_id,
        channel=body.channel,
        config=config,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return _resp(cfg)


@router.get("/channels")
async def get_alert_channels(org: Organization = Depends(get_current_org_from_jwt)):
    return {
        "plan": org.plan,
        "subscription_status": org.subscription_status,
        "effective_plan": effective_alert_plan(org.plan, org.subscription_status),
        "channels": channels_for_org(org.plan, org.subscription_status),
    }


@router.get("", response_model=list[AlertConfigResponse])
async def list_alert_configs(
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    configs = (await db.scalars(
        select(AlertConfig).where(AlertConfig.org_id == org.id, AlertConfig.is_active == True)
    )).all()
    return [_resp(c) for c in configs]


@router.delete("/{config_id}", status_code=204)
async def delete_alert_config(
    config_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    cfg = await _get_config_or_404(config_id, org, db)
    cfg.is_active = False  # soft delete
    await db.commit()


@router.post("/{config_id}/test", status_code=200)
async def test_alert_config(
    config_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Send a test alert to verify the channel config is valid."""
    cfg = await _get_config_or_404(config_id, org, db)
    from app.services.alert import dispatch_alert

    class _FakeIncident:
        id = "test-00000000"
        severity = "P3"
        status = "open"
        title = "Panopta test alert — configuration verified"
        fired_checks = []
        table_id = None
        org_id = None
        llm_narration = None
        from datetime import datetime, timezone
        created_at = datetime.now(timezone.utc)
        resolved_at = None

    if not cfg.is_active:
        raise HTTPException(status_code=410, detail="This alert route is deleted and cannot be tested.")
    if not channel_available(org.plan, org.subscription_status, cfg.channel):
        raise HTTPException(status_code=402, detail=channel_upgrade_detail(org.plan, org.subscription_status, cfg.channel))

    ok = dispatch_alert(cfg, _FakeIncident(), {"summary": "This is a Panopta test alert. No incident was created."})

    if not ok:
        label = CHANNELS.get(cfg.channel, {}).get("label", cfg.channel)
        raise HTTPException(status_code=502, detail=f"Test {label} alert failed. Check the route credentials, destination permissions, and minimum severity.")
    return {"sent": True, "channel": cfg.channel, "message": f"Test {CHANNELS[cfg.channel]['label']} alert sent."}
