"""
Test infrastructure.

Uses a real Postgres test DB (datawatch_test) — isolated from dev.
Set TEST_DATABASE_URL to override. Tests skip if DB is unreachable.

Fixtures:
  db_session   — AsyncSession, rolls back after each test
  client       — httpx AsyncClient against the FastAPI app
  test_org     — registered org with API key
  auth_headers — {"Authorization": "Bearer <jwt>"}
"""
import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Test DB URL ────────────────────────────────────────────────────────────────
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://datawatch:datawatch@localhost:5432/datawatch_test",
)

# Patch settings BEFORE importing the app
os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
os.environ.setdefault("SECRET_KEY", "test-secret-key-" + "x" * 20)
os.environ.setdefault("FERNET_MASTER_KEY", "dGVzdC1mZXJuZXQta2V5LXBhZGRlZC10by0zMmJ5dGVzISE=")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")  # DB 1 = test
os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ENVIRONMENT", "test")

from app.database import Base
from app.main import app
from app.config import settings


# ── Engine ─────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    except Exception as e:
        pytest.skip(f"Test DB unavailable: {e}")
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncSession:
    """Fresh DB contents per test.

    API routes commit during tests, so wrapping the fixture in a transaction makes
    later requests fail with "closed transaction" errors. Recreate metadata for
    reliable isolation instead.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
        await session.rollback()


# ── FastAPI client ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_session):
    """
    httpx AsyncClient wired to the FastAPI app.
    Overrides the get_db dependency to use the test session.
    """
    from app.database import get_db

    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db

    # Suppress scheduler startup in tests
    with patch("app.scheduler.start_scheduler", new_callable=AsyncMock), \
         patch("app.scheduler.stop_scheduler", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c

    app.dependency_overrides.clear()


# ── Org + auth ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_org(client):
    """Create a fresh org + user, return (org_data, api_key, email, password)."""
    slug = f"testorg-{uuid.uuid4().hex[:8]}"
    email = f"admin@{slug}.com"
    password = "testpassword123"

    resp = await client.post("/auth/register", json={
        "org_name": "Test Org",
        "org_slug": slug,
        "email": email,
        "password": password,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return {
        "org_id": data["org_id"],
        "org_slug": data["org_slug"],
        "api_key": data.get("api_key"),
        "email": email,
        "password": password,
    }


@pytest_asyncio.fixture
async def auth_headers(client, test_org):
    """JWT Bearer auth headers."""
    from app.routers import auth as auth_router
    auth_router._rate_store.clear()
    resp = await client.post("/auth/login", json={
        "org_slug": test_org["org_slug"],
        "email": test_org["email"],
        "password": test_org["password"],
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Profile seeding helper ─────────────────────────────────────────────────────

async def seed_profiles(db_session, table_id: str, days: int = 30,
                         row_count: int = 500, fingerprint: str = "fp_abc123") -> list:
    """Insert synthetic TableProfile records directly into DB."""
    import uuid
    from datetime import UTC, datetime, timedelta
    from app.models.table_profile import TableProfile

    profiles = []
    for i in range(days):
        collected_at = datetime.now(UTC) - timedelta(days=days - i)
        import random
        rc = max(1, int(random.gauss(row_count, row_count * 0.05)))
        p = TableProfile(
            id=uuid.uuid4(),
            table_id=table_id,
            collected_at=collected_at,
            row_count=rc,
            freshness_seconds=3600.0,
            schema_fingerprint=fingerprint,
            column_metrics={"amount": {"null_rate": 0.01, "mean": 150.0, "stddev": 50.0}},
            profiling_duration_ms=200,
        )
        db_session.add(p)
        profiles.append(p)
    await db_session.flush()
    return profiles


# ── LLM mock fixture ───────────────────────────────────────────────────────────

MOCK_NARRATION = {
    "summary": "The orders table stopped receiving data, indicating a pipeline failure.",
    "likely_causes": [
        {"hypothesis": "ETL job failed or was stopped", "probability": "high"},
        {"hypothesis": "Source database connection issue", "probability": "medium"},
    ],
    "impact_assessment": "No new orders are being tracked. Revenue reporting will be incomplete.",
    "recommended_actions": [
        "Check the ETL job logs for errors",
        "Verify the source database connection",
        "Review pipeline scheduler status",
    ],
    "data_pattern_notes": "Row count was stable at ~500/day for 30 days before dropping to 0.",
    "confidence": "high",
}
