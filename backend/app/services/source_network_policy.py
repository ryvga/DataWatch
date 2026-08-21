"""Network and local-file policy for user-configured data sources."""

import asyncio
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.config import settings


_HOST_FIELDS = {
    "databricks": "server_hostname",
}
_LOCAL_CONNECTORS = {"duckdb", "sqlite"}


def _mongo_hosts(uri: str) -> list[str]:
    parsed = urlsplit(uri)
    if parsed.scheme not in {"mongodb", "mongodb+srv"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="MongoDB URI is invalid")
    authority = parsed.netloc.rsplit("@", 1)[-1]
    hosts: list[str] = []
    for address in authority.split(","):
        address = address.strip()
        if address.startswith("["):
            end = address.find("]")
            host = address[1:end] if end > 0 else ""
        else:
            host = address.rsplit(":", 1)[0] if address.count(":") == 1 else address
        if not host:
            raise HTTPException(status_code=400, detail="MongoDB URI is invalid")
        hosts.append(host)
    return hosts


def source_hosts(source_type: str, config: dict) -> list[str]:
    """Return only connection hostnames; credentials are never included."""
    if source_type == "mongodb":
        return _mongo_hosts(str(config.get("uri", "")))
    if source_type == "cassandra":
        raw = config.get("hosts", "")
        values = raw if isinstance(raw, list) else str(raw).split(",")
        return [str(value).strip() for value in values if str(value).strip()]
    field = _HOST_FIELDS.get(source_type, "host")
    value = config.get(field)
    return [str(value).strip()] if value else []


def _address_is_denied(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.is_loopback:
        return settings.is_production and not settings.SOURCE_ALLOW_PRIVATE_NETWORKS
    if (
        address.is_unspecified
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
    ):
        return True
    return (
        settings.is_production
        and address.is_private
        and not settings.SOURCE_ALLOW_PRIVATE_NETWORKS
    )


async def _resolve(host: str) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        records = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail="Source hostname could not be resolved") from exc
    return {ipaddress.ip_address(record[4][0]) for record in records}


def _validate_local_path(source_type: str, config: dict) -> None:
    if source_type not in _LOCAL_CONNECTORS or not settings.is_production:
        return
    configured_root = settings.SOURCE_LOCAL_PATH_ROOT.strip()
    if not configured_root:
        raise HTTPException(
            status_code=403,
            detail="Local-file data sources are disabled in this deployment",
        )
    candidate = Path(str(config.get("path", ""))).expanduser().resolve(strict=False)
    root = Path(configured_root).expanduser().resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=403, detail="Source path is outside the configured root")


async def enforce_source_target_policy(source_type: str, config: dict) -> None:
    """Reject local/metadata/private egress unless deployment policy allows it."""
    _validate_local_path(source_type, config)
    for host in source_hosts(source_type, config):
        addresses = await _resolve(host)
        if not addresses or any(_address_is_denied(address) for address in addresses):
            raise HTTPException(status_code=403, detail="Source network target is not allowed")
