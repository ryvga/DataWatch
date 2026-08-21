from types import SimpleNamespace

import ipaddress
import pytest
from fastapi import HTTPException

from app.services import source_network_policy as policy


@pytest.mark.asyncio
async def test_production_rejects_private_and_metadata_targets(monkeypatch):
    monkeypatch.setattr(
        policy,
        "settings",
        SimpleNamespace(
            is_production=True,
            SOURCE_ALLOW_PRIVATE_NETWORKS=False,
            SOURCE_LOCAL_PATH_ROOT="",
        ),
    )

    async def private_resolver(_host):
        return {ipaddress.ip_address("10.20.30.40")}

    monkeypatch.setattr(policy, "_resolve", private_resolver)
    with pytest.raises(HTTPException) as private_error:
        await policy.enforce_source_target_policy("postgres", {"host": "internal-db"})
    assert private_error.value.status_code == 403

    async def metadata_resolver(_host):
        return {ipaddress.ip_address("169.254.169.254")}

    monkeypatch.setattr(policy, "_resolve", metadata_resolver)
    with pytest.raises(HTTPException) as metadata_error:
        await policy.enforce_source_target_policy("postgres", {"host": "metadata"})
    assert metadata_error.value.status_code == 403


@pytest.mark.asyncio
async def test_production_private_network_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(
        policy,
        "settings",
        SimpleNamespace(
            is_production=True,
            SOURCE_ALLOW_PRIVATE_NETWORKS=True,
            SOURCE_LOCAL_PATH_ROOT="",
        ),
    )

    async def resolver(_host):
        return {ipaddress.ip_address("10.20.30.40")}

    monkeypatch.setattr(policy, "_resolve", resolver)
    await policy.enforce_source_target_policy("postgres", {"host": "internal-db"})


@pytest.mark.asyncio
async def test_all_dns_answers_must_pass_policy(monkeypatch):
    monkeypatch.setattr(
        policy,
        "settings",
        SimpleNamespace(
            is_production=True,
            SOURCE_ALLOW_PRIVATE_NETWORKS=False,
            SOURCE_LOCAL_PATH_ROOT="",
        ),
    )

    async def resolver(_host):
        return {
            ipaddress.ip_address("203.0.113.8"),
            ipaddress.ip_address("127.0.0.1"),
        }

    monkeypatch.setattr(policy, "_resolve", resolver)
    with pytest.raises(HTTPException) as exc_info:
        await policy.enforce_source_target_policy("postgres", {"host": "rebinding.example"})
    assert exc_info.value.status_code == 403


def test_mongodb_host_extraction_never_returns_credentials():
    hosts = policy.source_hosts(
        "mongodb",
        {"uri": "mongodb://admin:secret@db1.example.com:27017,db2.example.com/app"},
    )
    assert hosts == ["db1.example.com", "db2.example.com"]
    assert all("admin" not in host and "secret" not in host for host in hosts)


@pytest.mark.asyncio
async def test_production_local_database_is_confined(monkeypatch, tmp_path):
    allowed = tmp_path / "sources"
    monkeypatch.setattr(
        policy,
        "settings",
        SimpleNamespace(
            is_production=True,
            SOURCE_ALLOW_PRIVATE_NETWORKS=False,
            SOURCE_LOCAL_PATH_ROOT=str(allowed),
        ),
    )
    await policy.enforce_source_target_policy(
        "sqlite", {"path": str(allowed / "analytics.sqlite")}
    )
    with pytest.raises(HTTPException) as exc_info:
        await policy.enforce_source_target_policy(
            "sqlite", {"path": str(tmp_path / "secrets.sqlite")}
        )
    assert exc_info.value.status_code == 403
