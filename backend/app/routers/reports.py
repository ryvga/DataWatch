"""Reports and AI monitoring assistant endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.organization import Organization
from app.routers.auth import get_current_org_from_jwt
from app.services.reports import ReportService

router = APIRouter(prefix="/api/v1", tags=["reports"])


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/reports/weekly")
async def get_weekly_report(
    window_days: int = 7,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    return await ReportService.generate_weekly_report(org.id, db, window_days=window_days)


@router.get("/reports/incident/{incident_id}")
async def get_incident_report(
    incident_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    from app.models.incident import Incident
    from sqlalchemy import select

    # Verify ownership
    incident = await db.scalar(
        select(Incident).where(Incident.id == incident_id, Incident.org_id == org.id)
    )
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return await ReportService.generate_incident_report(incident_id, db)


# ── AI Monitor Recommender ────────────────────────────────────────────────────

class RecommendMonitorsRequest(BaseModel):
    source_id: str = ""  # ignored — comes from URL path
    table_name: str
    schema_name: str = "public"


@router.post("/sources/{source_id}/recommend-monitors")
async def recommend_monitors(
    source_id: str,
    body: RecommendMonitorsRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select
    from app.models.data_source import DataSource
    from app.services.crypto import decrypt_config
    from app.connectors.factory import ConnectorFactory
    from app.services.profiler import ProfilerService
    from app.services.monitor_recommender import recommend_monitors as _recommend
    from app.services.crypto import CryptoService

    source = await db.scalar(
        select(DataSource).where(DataSource.id == source_id, DataSource.org_id == org.id)
    )
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Resolve per-org LLM key
    org_llm_key = None
    org_model = None
    if org.llm_api_key_encrypted:
        try:
            org_llm_key = CryptoService().decrypt_for_org(org.llm_api_key_encrypted, str(org.id))
            org_model = org.llm_model
        except Exception:
            pass

    try:
        config = decrypt_config(source.connection_config["encrypted"], str(org.id))
        connector = ConnectorFactory.create(source.type, config)
        profiler = ProfilerService()
        columns = await profiler._get_columns_raw(connector, body.schema_name, body.table_name)
        await connector.close()

        col_dicts = [
            {
                "name": c.name,
                "data_type": c.data_type,
                "category": c.category,
                "nullable": c.is_nullable,
            }
            for c in columns
        ]

        monitors = await _recommend(
            table_name=body.table_name,
            columns=col_dicts,
            org_llm_key=org_llm_key,
            org_model=org_model,
            db_type=source.type,
        )
        return {"table": body.table_name, "recommendations": monitors, "count": len(monitors)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {e}")


# ── Natural Language Rule Builder ─────────────────────────────────────────────

class NLRuleRequest(BaseModel):
    rule: str
    table_name: str
    columns: list[dict] = []


@router.post("/tables/{table_id}/nl-rule")
async def natural_language_rule(
    table_id: str,
    body: NLRuleRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    from app.services.monitor_recommender import nl_rule_to_sql
    from app.services.crypto import CryptoService

    org_llm_key = None
    org_model = None
    if org.llm_api_key_encrypted:
        try:
            org_llm_key = CryptoService().decrypt_for_org(org.llm_api_key_encrypted, str(org.id))
            org_model = org.llm_model
        except Exception:
            pass

    result = await nl_rule_to_sql(
        natural_language_rule=body.rule,
        table_name=body.table_name,
        columns=body.columns,
        org_llm_key=org_llm_key,
        org_model=org_model,
    )
    return result
