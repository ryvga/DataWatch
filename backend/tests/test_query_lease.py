import pytest

from app.services import query_lease


class FakeRedis:
    def __init__(self, acquired=True, set_error=None):
        self.acquired = acquired
        self.set_error = set_error
        self.calls = []

    async def set(self, key, token, **kwargs):
        self.calls.append(("set", key, token, kwargs))
        if self.set_error:
            raise self.set_error
        return self.acquired

    async def eval(self, script, count, key, token):
        self.calls.append(("eval", count, key, token, script))
        return 1

    async def aclose(self):
        self.calls.append(("close",))


@pytest.mark.asyncio
async def test_source_query_lease_is_tenant_scoped_and_token_released(monkeypatch):
    redis_client = FakeRedis()
    monkeypatch.setattr(
        query_lease.aioredis,
        "from_url",
        lambda *_args, **_kwargs: redis_client,
    )

    async with query_lease.source_query_lease(
        "org-1", "source-7", ttl_seconds=45
    ):
        assert redis_client.calls[0][0] == "set"

    set_call, eval_call, close_call = redis_client.calls
    assert set_call[1] == "lease:source_query:org-1:source-7"
    assert set_call[3] == {"nx": True, "ex": 45}
    assert eval_call[0] == "eval"
    assert eval_call[2] == set_call[1]
    assert eval_call[3] == set_call[2]
    assert close_call == ("close",)


@pytest.mark.asyncio
async def test_source_query_lease_rejects_concurrency_and_fails_closed(monkeypatch):
    for redis_client, code in (
        (FakeRedis(acquired=False), "query_concurrency_exceeded"),
        (FakeRedis(set_error=ConnectionError()), "query_lease_unavailable"),
    ):
        monkeypatch.setattr(
            query_lease.aioredis,
            "from_url",
            lambda *_args, client=redis_client, **_kwargs: client,
        )
        with pytest.raises(query_lease.QueryLeaseError) as exc:
            async with query_lease.source_query_lease(
                "org-1", "source-7", ttl_seconds=45
            ):
                pytest.fail("lease must not be acquired")
        assert exc.value.code == code
        assert redis_client.calls[-1] == ("close",)
