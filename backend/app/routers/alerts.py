from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert_config import AlertConfig
from app.models.organization import Organization
from app.routers.auth import get_current_org_from_jwt

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resp(a: AlertConfig) -> AlertConfigResponse:
    return AlertConfigResponse(
        id=str(a.id),
        table_id=str(a.table_id) if a.table_id else None,
        channel=a.channel,
        config=a.config,
        is_active=a.is_active,
    )


async def _get_config_or_404(config_id: str, org: Organization, db: AsyncSession) -> AlertConfig:
    cfg = await db.scalar(
        select(AlertConfig).where(AlertConfig.id == config_id, AlertConfig.org_id == org.id)
    )
    if not cfg:
        raise HTTPException(status_code=404, detail="Alert config not found")
    return cfg


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=AlertConfigResponse, status_code=201)
async def create_alert_config(
    body: AlertConfigCreate,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    valid_channels = {"slack", "email", "pagerduty"}
    if body.channel not in valid_channels:
        raise HTTPException(status_code=400, detail=f"channel must be one of {valid_channels}")

    cfg = AlertConfig(
        org_id=org.id,
        table_id=body.table_id,
        channel=body.channel,
        config=body.config,
        is_active=True,
    )
    db.add(cfg)
    await db.flush()
    return _resp(cfg)


@router.get("", response_model=list[AlertConfigResponse])
async def list_alert_configs(
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    configs = (await db.scalars(
        select(AlertConfig).where(AlertConfig.org_id == org.id)
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


@router.post("/{config_id}/test", status_code=200)
async def test_alert_config(
    config_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    """Send a test alert to verify the channel config is valid."""
    cfg = await _get_config_or_404(config_id, org, db)
    from app.services.alert import send_email_alert, send_pagerduty_alert, send_slack_alert

    class _FakeIncident:
        id = "test-00000000"
        severity = "P3"
        title = "DataWatch test alert — configuration verified"
        fired_checks = []
        from datetime import datetime, timezone
        created_at = datetime.now(timezone.utc)

    ok = False
    channel = cfg.channel
    c = cfg.config or {}

    if channel == "slack":
        ok = send_slack_alert(c.get("webhook_url", ""), _FakeIncident(), None)
    elif channel == "email":
        ok = send_email_alert(c.get("to", []), _FakeIncident(), None)
    elif channel == "pagerduty":
        ok = send_pagerduty_alert(c.get("routing_key", ""), _FakeIncident(), "trigger")

    if not ok:
        raise HTTPException(status_code=502, detail=f"Test {channel} alert failed — check config")
    return {"sent": True, "channel": channel}
