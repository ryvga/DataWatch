import json
import logging
import time
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.connectors.factory import ConnectorFactory
from app.database import get_db
from app.models.data_source import DataSource
from app.models.organization import Organization
from app.routers.auth import get_current_org_from_api_key, get_current_org_from_jwt
from app.services.crypto import decrypt_config, encrypt_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sources", tags=["sources"])

DISCOVERY_TTL = 1800  # 30 min


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class DataSourceCreate(BaseModel):
    name: str
    type: str  # postgres | bigquery | snowflake | duckdb
    connection_config: dict  # NEVER returned in responses


class DataSourceResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    last_connected_at: datetime | None

    model_config = {"from_attributes": True}


class TestResult(BaseModel):
    connected: bool
    latency_ms: int
    error: str | None = None


class TableInfoSchema(BaseModel):
    name: str
    estimated_rows: int | None


class SchemaInfoSchema(BaseModel):
    name: str
    tables: list[TableInfoSchema]


class DiscoveryResponse(BaseModel):
    schemas: list[SchemaInfoSchema]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_source_or_404(source_id: str, org: Organization, db: AsyncSession) -> DataSource:
    src = await db.scalar(
        select(DataSource).where(DataSource.id == source_id, DataSource.org_id == org.id)
    )
    if not src:
        raise HTTPException(status_code=404, detail="Data source not found")
    return src


async def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=DataSourceResponse, status_code=201)
async def create_source(
    body: DataSourceCreate,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    # Validate type
    valid_types = {"postgres", "bigquery", "snowflake", "duckdb"}
    if body.type not in valid_types:
        raise HTTPException(status_code=400, detail=f"type must be one of {valid_types}")

    # Enforce plan limit
    from app.services.plans import enforce_source_limit
    await enforce_source_limit(org, db)

    encrypted = encrypt_config(body.connection_config, str(org.id))
    src = DataSource(
        org_id=org.id,
        name=body.name,
        type=body.type,
        connection_config={"encrypted": encrypted},
        status="pending",
    )
    db.add(src)
    await db.flush()

    # Test connection inline, update status
    status = "error"
    try:
        if body.type == "snowflake":
            status = "stub"
        else:
            connector = ConnectorFactory.create(body.type, body.connection_config)
            ok = await connector.test_connection()
            await connector.close()
            status = "connected" if ok else "error"
    except NotImplementedError:
        status = "stub"
    except Exception as e:
        logger.warning("Source connection test failed during create: %s", type(e).__name__)
        status = "error"

    src.status = status
    if status == "connected":
        src.last_connected_at = datetime.now(timezone.utc)

    return DataSourceResponse(
        id=str(src.id),
        name=src.name,
        type=src.type,
        status=src.status,
        last_connected_at=src.last_connected_at,
    )


@router.get("", response_model=list[DataSourceResponse])
async def list_sources(
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    sources = (await db.scalars(
        select(DataSource).where(DataSource.org_id == org.id)
    )).all()
    return [DataSourceResponse(
        id=str(s.id), name=s.name, type=s.type,
        status=s.status, last_connected_at=s.last_connected_at,
    ) for s in sources]


@router.get("/{source_id}", response_model=DataSourceResponse)
async def get_source(
    source_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    src = await _get_source_or_404(source_id, org, db)
    return DataSourceResponse(
        id=str(src.id), name=src.name, type=src.type,
        status=src.status, last_connected_at=src.last_connected_at,
    )


@router.delete("/{source_id}", status_code=204)
async def pause_source(
    source_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    src = await _get_source_or_404(source_id, org, db)
    src.status = "paused"  # soft delete — preserves profile history


@router.post("/{source_id}/test", response_model=TestResult)
async def test_source(
    source_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    src = await _get_source_or_404(source_id, org, db)

    if src.type == "snowflake":
        raise HTTPException(status_code=501, detail="Snowflake connector coming soon")

    try:
        config = decrypt_config(src.connection_config["encrypted"], str(org.id))
        connector = ConnectorFactory.create(src.type, config)
        start = time.monotonic()
        ok = await connector.test_connection()
        latency_ms = int((time.monotonic() - start) * 1000)
        await connector.close()

        status = "connected" if ok else "error"
        src.status = status
        if ok:
            src.last_connected_at = datetime.now(timezone.utc)

        return TestResult(connected=ok, latency_ms=latency_ms)
    except Exception as e:
        logger.warning("Source test error: %s", type(e).__name__)
        return TestResult(connected=False, latency_ms=0, error=str(e))


@router.post("/{source_id}/discover", response_model=DiscoveryResponse)
async def discover_source(
    source_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    src = await _get_source_or_404(source_id, org, db)

    if src.type == "snowflake":
        raise HTTPException(status_code=501, detail="Snowflake connector coming soon")

    config = decrypt_config(src.connection_config["encrypted"], str(org.id))
    connector = ConnectorFactory.create(src.type, config)
    try:
        schemas = await connector.discover_schemas()
    finally:
        await connector.close()

    result = {
        "schemas": [
            {"name": s.name, "tables": [{"name": t.name, "estimated_rows": t.estimated_rows}
                                        for t in s.tables]}
            for s in schemas
        ]
    }

    # Cache in Redis for 30 min
    r = await _redis()
    await r.setex(f"discovery:{source_id}", DISCOVERY_TTL, json.dumps(result))
    await r.aclose()

    return DiscoveryResponse(**result)


@router.get("/connector-types", tags=["sources"])
async def get_connector_types():
    """Return metadata for all supported connector types (for UI forms)."""
    return ConnectorFactory.supported_types()


@router.get("/{source_id}/schemas", response_model=DiscoveryResponse)
async def get_schemas(
    source_id: str,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    # Try cache first
    r = await _redis()
    cached = await r.get(f"discovery:{source_id}")
    await r.aclose()

    if cached:
        return DiscoveryResponse(**json.loads(cached))

    # Cache miss — trigger fresh discovery
    return await discover_source(source_id, org, db)
