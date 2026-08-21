import json
from unittest.mock import AsyncMock

import pytest

from app import main


@pytest.mark.asyncio
async def test_readiness_returns_200_when_required_dependencies_are_connected(monkeypatch):
    monkeypatch.setattr(
        main,
        "_dependency_health",
        AsyncMock(return_value={"db": "connected", "redis": "connected"}),
    )

    response = await main.readiness()

    assert response.status_code == 200
    assert json.loads(response.body) == {
        "status": "ready",
        "db": "connected",
        "redis": "connected",
    }


@pytest.mark.asyncio
async def test_readiness_returns_503_when_a_required_dependency_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        main,
        "_dependency_health",
        AsyncMock(return_value={"db": "connected", "redis": "disconnected"}),
    )

    response = await main.readiness()

    assert response.status_code == 503
    assert json.loads(response.body) == {
        "status": "not_ready",
        "db": "connected",
        "redis": "disconnected",
    }
