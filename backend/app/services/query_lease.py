"""Distributed per-tenant/source query execution lease."""

import secrets
from contextlib import asynccontextmanager

import redis.asyncio as aioredis

from app.config import settings


class QueryLeaseError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@asynccontextmanager
async def source_query_lease(
    org_id: str,
    source_id: str,
    *,
    ttl_seconds: int,
):
    """Allow one bounded query per source across all API/worker processes."""
    token = secrets.token_urlsafe(24)
    key = f"lease:source_query:{org_id}:{source_id}"
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    acquired = False
    try:
        try:
            acquired = bool(
                await redis_client.set(
                    key,
                    token,
                    nx=True,
                    ex=max(5, min(ttl_seconds, 300)),
                )
            )
        except Exception as exc:
            raise QueryLeaseError(
                "query_lease_unavailable",
                "Shared query capacity control is unavailable",
            ) from exc
        if not acquired:
            raise QueryLeaseError(
                "query_concurrency_exceeded",
                "Another query is already running for this source",
            )
        yield
    finally:
        if acquired:
            try:
                await redis_client.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then "
                    "return redis.call('del', KEYS[1]) else return 0 end",
                    1,
                    key,
                    token,
                )
            except Exception:
                # TTL remains the final safety net; never hide the query result.
                pass
        await redis_client.aclose()
