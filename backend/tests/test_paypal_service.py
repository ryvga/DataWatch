from types import SimpleNamespace

from app.services.paypal import PayPalClient


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {}
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_paypal_client_caches_access_token_and_creates_order(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def post(self, path, **kwargs):
            calls.append((path, kwargs))
            if path == "/v1/oauth2/token":
                return FakeResponse({"access_token": "token-1", "expires_in": 3600})
            if path == "/v2/checkout/orders":
                return FakeResponse({
                    "id": "ORDER-123",
                    "links": [
                        {"rel": "self", "href": "https://api.example/orders/ORDER-123"},
                        {"rel": "approve", "href": "https://paypal.example/approve"},
                    ],
                })
            raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr("app.services.paypal.httpx.Client", FakeClient)

    client = PayPalClient(
        client_id="client-id",
        client_secret="client-secret",
        base_url="https://api-m.sandbox.paypal.com",
    )

    assert client.get_access_token() == "token-1"
    order = client.create_order(
        amount_usd=49.0,
        description="DataWatch starter monthly",
        return_url="https://example.com/return",
        cancel_url="https://example.com/cancel",
    )

    assert order == {"id": "ORDER-123", "approval_url": "https://paypal.example/approve"}
    assert [call[0] for call in calls].count("/v1/oauth2/token") == 1
    order_payload = calls[-1][1]["json"]
    assert order_payload["purchase_units"][0]["amount"]["value"] == "49.00"
    assert calls[-1][1]["headers"]["Authorization"] == "Bearer token-1"

