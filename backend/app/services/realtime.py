"""Org-scoped realtime events over Redis pub/sub.

Workers and the API process do not share memory in production, so events are
published through Redis and fanned out to WebSocket clients connected to the
API process. The payload is deliberately small and versioned; clients should
refetch authoritative records after receiving an event.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger(__name__)

EVENT_CHANNEL = "datawatch:realtime:v1"


def build_event(org_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a JSON-safe event envelope for the browser client."""
    return {
        "version": 1,
        "id": f"{org_id}:{event_type}:{datetime.now(UTC).timestamp():.6f}",
        "type": event_type,
        "orgId": str(org_id),
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": payload or {},
    }


async def publish_event(org_id: str, event_type: str, payload: dict[str, Any] | None = None) -> bool:
    """Publish an event without making the caller dependent on Redis health."""
    event = build_event(str(org_id), event_type, payload)
    client = None
    try:
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.publish(EVENT_CHANNEL, json.dumps(event, default=str, separators=(",", ":")))
        return True
    except Exception as exc:  # realtime is an enhancement; never fail data writes
        logger.warning("Realtime event publish failed for %s: %s", event_type, type(exc).__name__)
        return False
    finally:
        if client is not None:
            await client.aclose()


class RealtimeManager:
    """Manage local WebSocket clients and one Redis subscriber task."""

    def __init__(self) -> None:
        self._clients: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._listener_task: asyncio.Task | None = None
        self._listener_loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket, org_id: str) -> None:
        await websocket.accept()
        async with self._lock:
            self._clients.setdefault(str(org_id), set()).add(websocket)
            if self._listener_task is None or self._listener_task.done():
                self._listener_loop = asyncio.get_running_loop()
                self._listener_task = asyncio.create_task(self._listen(), name="datawatch-realtime-listener")
        await websocket.send_json(build_event(str(org_id), "realtime.connected", {"transport": "websocket"}))

    async def disconnect(self, websocket: WebSocket, org_id: str) -> None:
        async with self._lock:
            clients = self._clients.get(str(org_id))
            if clients:
                clients.discard(websocket)
                if not clients:
                    self._clients.pop(str(org_id), None)
            if not self._clients and self._listener_task and not self._listener_task.done():
                self._listener_task.cancel()
                self._listener_task = None

    async def shutdown(self) -> None:
        async with self._lock:
            task = self._listener_task
            self._listener_task = None
            self._clients.clear()
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _listen(self) -> None:
        client = None
        pubsub = None
        try:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(EVENT_CHANNEL)
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message or message.get("type") != "message":
                    await asyncio.sleep(0)
                    continue
                try:
                    event = json.loads(message["data"])
                    await self.broadcast(str(event["orgId"]), event)
                except (KeyError, TypeError, ValueError):
                    logger.warning("Discarded malformed realtime event")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Realtime Redis listener stopped: %s", type(exc).__name__)
        finally:
            if pubsub is not None:
                await pubsub.close()
            if client is not None:
                await client.aclose()

    async def broadcast(self, org_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients.get(str(org_id), set()))
        stale: list[WebSocket] = []
        for websocket in clients:
            try:
                await websocket.send_json(event)
            except Exception:
                stale.append(websocket)
        if stale:
            async with self._lock:
                active = self._clients.get(str(org_id), set())
                for websocket in stale:
                    active.discard(websocket)


realtime_manager = RealtimeManager()
