import json
from types import SimpleNamespace

import pytest

from app.services import realtime


class _Redis:
    def __init__(self):
        self.published = []
        self.closed = False

    async def publish(self, channel, message):
        self.published.append((channel, message))

    async def aclose(self):
        self.closed = True


class _Socket:
    def __init__(self, fail=False):
        self.events = []
        self.fail = fail

    async def send_json(self, event):
        if self.fail:
            raise RuntimeError("socket closed")
        self.events.append(event)


def test_build_event_has_versioned_org_scoped_envelope():
    event = realtime.build_event("org-1", "incident.updated", {"status": "open"})
    assert event["version"] == 1
    assert event["orgId"] == "org-1"
    assert event["type"] == "incident.updated"
    assert event["payload"] == {"status": "open"}
    assert event["id"].startswith("org-1:incident.updated:")


@pytest.mark.asyncio
async def test_publish_event_is_best_effort_and_serializes_scalars(monkeypatch):
    redis = _Redis()
    monkeypatch.setattr(realtime.aioredis, "from_url", lambda *args, **kwargs: redis)

    ok = await realtime.publish_event("org-1", "profile.completed", {"profileId": SimpleNamespace(id=3)})

    assert ok is True
    assert redis.closed is True
    channel, message = redis.published[0]
    assert channel == realtime.EVENT_CHANNEL
    payload = json.loads(message)
    assert payload["orgId"] == "org-1"
    assert payload["payload"]["profileId"] == "namespace(id=3)"


@pytest.mark.asyncio
async def test_broadcast_delivers_only_to_org_and_prunes_dead_sockets():
    manager = realtime.RealtimeManager()
    live = _Socket()
    dead = _Socket(fail=True)
    other = _Socket()
    manager._clients = {"org-1": {live, dead}, "org-2": {other}}

    await manager.broadcast("org-1", {"type": "incident.updated"})

    assert live.events == [{"type": "incident.updated"}]
    assert other.events == []
    assert dead not in manager._clients["org-1"]
