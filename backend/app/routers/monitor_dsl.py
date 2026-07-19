"""Validation-only API for the safe monitor DSL."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.factory import ConnectorFactory
from app.database import get_db
from app.models.data_source import DataSource
from app.models.monitored_table import MonitoredTable
from app.models.organization import Organization
from app.routers.auth import get_current_org_from_jwt
from app.services.monitor_dsl import (
    MonitorDefinition,
    definition_hash,
    predicate_stats,
)

router = APIRouter(prefix="/api/v2/monitors", tags=["monitor_dsl"])


@router.post("/validate")
async def validate_monitor_definition(
    definition: MonitorDefinition,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    table = await db.scalar(
        select(MonitoredTable)
        .join(DataSource, DataSource.id == MonitoredTable.source_id)
        .where(
            MonitoredTable.id == definition.spec.target.asset_id,
            DataSource.org_id == org.id,
        )
    )
    if not table:
        raise HTTPException(status_code=404, detail="Target asset not found")
    source = await db.get(DataSource, table.source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Target asset not found")

    capabilities = ConnectorFactory.capabilities_for(source.type)
    requirements = sorted({measurement.type for measurement in definition.spec.measurements})
    unsupported = []
    if capabilities["profiling"] == "none":
        unsupported.append("connector_has_no_profile_runtime")
    unsupported.append("dsl_compiler_not_implemented")

    return {
        "valid": True,
        "apiVersion": definition.api_version,
        "definitionHash": definition_hash(definition),
        "canonicalDefinition": definition.model_dump(mode="json", by_alias=True),
        "stats": {
            "measurements": len(definition.spec.measurements),
            **predicate_stats(definition),
        },
        "capabilityPlan": {
            "sourceType": source.type,
            "requirements": requirements,
            "compatible": not unsupported,
            "unsupported": unsupported,
            "activationSupported": False,
        },
    }
