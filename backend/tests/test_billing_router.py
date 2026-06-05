from types import SimpleNamespace

import pytest

from app.routers import billing


class FakeDb:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        return None


@pytest.mark.asyncio
async def test_create_order_uses_plan_price_and_paypal_checkout(monkeypatch):
    calls = {}

    class FakePayPal:
        def create_order(self, amount_usd, description, return_url, cancel_url):
            calls["order"] = (amount_usd, description, return_url, cancel_url)
            return {"id": "ORDER-123", "approval_url": "https://paypal.example/approve"}

    monkeypatch.setattr(billing, "paypal_client", FakePayPal())

    org = SimpleNamespace(slug="acme")
    result = await billing.create_order(
        billing.CreateBillingRequest(plan="starter", billing_period="monthly"),
        org=org,
    )

    assert result.order_id == "ORDER-123"
    assert result.approval_url == "https://paypal.example/approve"
    assert calls["order"][0] == 49.0
    assert "starter" in calls["order"][1]
    assert calls["order"][2] == "https://acme.datawatch.io/billing/paypal/return"


@pytest.mark.asyncio
async def test_capture_subscription_marks_org_active(monkeypatch):
    class FakePayPal:
        def get_subscription(self, subscription_id):
            assert subscription_id == "SUB-123"
            return {"id": "SUB-123", "status": "ACTIVE"}

    monkeypatch.setattr(billing, "paypal_client", FakePayPal())

    org = SimpleNamespace(
        plan="free",
        subscription_status="trialing",
        paypal_subscription_id=None,
        billing_period="yearly",
    )
    db = FakeDb()

    result = await billing.capture_subscription(
        billing.CaptureSubscriptionRequest(subscription_id="SUB-123", plan="growth"),
        org=org,
        db=db,
    )

    assert result["plan"] == "growth"
    assert result["subscription_status"] == "active"
    assert result["paypal_subscription_id"] == "SUB-123"
    assert result["billing_period"] == "yearly"
    assert db.committed is True
