from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.organization import Organization
from app.routers.auth import get_current_org_from_jwt
from app.services.paypal import PayPalError, paypal_client

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

PlanName = Literal["starter", "growth", "agency"]
BillingPeriod = Literal["monthly", "yearly"]

PLAN_PRICES: dict[str, dict[str, float]] = {
    "starter": {"monthly": 49.00, "yearly": 470.00},
    "growth": {"monthly": 149.00, "yearly": 1430.00},
    "agency": {"monthly": 299.00, "yearly": 2870.00},
}

_PERIOD_TO_PAYPAL_INTERVAL = {"monthly": "MONTH", "yearly": "YEAR"}


class CreateBillingRequest(BaseModel):
    plan: PlanName
    billing_period: BillingPeriod
    return_url: str | None = None
    cancel_url: str | None = None


class CreateOrderResponse(BaseModel):
    order_id: str
    approval_url: str


class CaptureOrderRequest(BaseModel):
    order_id: str


class CaptureSubscriptionRequest(BaseModel):
    subscription_id: str
    plan: PlanName
    billing_period: BillingPeriod | None = None


class CancelBillingRequest(BaseModel):
    reason: str = "Customer requested cancellation"


def _checkout_urls(org: Organization, return_url: str | None, cancel_url: str | None) -> tuple[str, str]:
    base = f"https://{org.slug}.{settings.BASE_DOMAIN}"
    return (
        return_url or f"{base}/billing/paypal/return",
        cancel_url or f"{base}/billing/paypal/cancel",
    )


def _paypal_description(plan: str, billing_period: str) -> str:
    return f"Panopta {plan} {billing_period} plan"


def _paypal_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"PayPal request failed: {exc}")


def _extract_order_plan_period(capture: dict[str, Any]) -> tuple[str, str]:
    candidates: list[str] = []
    for unit in capture.get("purchase_units", []):
        if unit.get("description"):
            candidates.append(unit["description"])
        if unit.get("custom_id"):
            candidates.append(unit["custom_id"])
        for payment in unit.get("payments", {}).get("captures", []):
            if payment.get("custom_id"):
                candidates.append(payment["custom_id"])

    text = " ".join(candidates).lower()
    plan = next((item for item in PLAN_PRICES if item in text), None)
    period = next((item for item in ("monthly", "yearly") if item in text), None)
    if not plan or not period:
        raise HTTPException(status_code=400, detail="Could not determine plan from PayPal order")
    return plan, period


def _next_billing_date(subscription: dict[str, Any] | None) -> str | None:
    if not subscription:
        return None
    billing_info = subscription.get("billing_info") or {}
    return billing_info.get("next_billing_time")


@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(
    body: CreateBillingRequest,
    org: Organization = Depends(get_current_org_from_jwt),
):
    amount = PLAN_PRICES[body.plan][body.billing_period]
    return_url, cancel_url = _checkout_urls(org, body.return_url, body.cancel_url)
    try:
        order = paypal_client.create_order(
            amount_usd=amount,
            description=_paypal_description(body.plan, body.billing_period),
            return_url=return_url,
            cancel_url=cancel_url,
        )
    except (PayPalError, httpx.HTTPError) as exc:
        raise _paypal_error(exc) from exc

    return CreateOrderResponse(order_id=order["id"], approval_url=order["approval_url"])


@router.post("/capture-order")
async def capture_order(
    body: CaptureOrderRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    try:
        capture = paypal_client.capture_order(body.order_id)
    except (PayPalError, httpx.HTTPError) as exc:
        raise _paypal_error(exc) from exc

    if capture.get("status") != "COMPLETED":
        raise HTTPException(status_code=400, detail="PayPal order is not completed")

    plan, billing_period = _extract_order_plan_period(capture)
    org.plan = plan
    org.billing_period = billing_period
    org.subscription_status = "active"
    await db.commit()
    await db.refresh(org)

    return {"success": True, "plan": org.plan, "subscription_status": org.subscription_status}


@router.post("/create-subscription")
async def create_subscription(
    body: CreateBillingRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    amount = PLAN_PRICES[body.plan][body.billing_period]
    interval = _PERIOD_TO_PAYPAL_INTERVAL[body.billing_period]
    return_url, cancel_url = _checkout_urls(org, body.return_url, body.cancel_url)

    try:
        plan_id = paypal_client.create_subscription_plan(
            name=_paypal_description(body.plan, body.billing_period),
            price_usd=amount,
            interval=interval,
        )
        subscription = paypal_client.create_subscription(plan_id, return_url, cancel_url)
    except (PayPalError, httpx.HTTPError) as exc:
        raise _paypal_error(exc) from exc

    org.paypal_subscription_id = subscription["id"]
    org.billing_period = body.billing_period
    org.subscription_status = "approval_pending"
    await db.commit()
    await db.refresh(org)

    return {"subscription_id": subscription["id"], "approval_url": subscription["approval_url"]}


@router.post("/capture-subscription")
async def capture_subscription(
    body: CaptureSubscriptionRequest,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    try:
        subscription = paypal_client.get_subscription(body.subscription_id)
    except (PayPalError, httpx.HTTPError) as exc:
        raise _paypal_error(exc) from exc

    if subscription.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="PayPal subscription is not active")

    org.plan = body.plan
    org.subscription_status = "active"
    org.paypal_subscription_id = body.subscription_id
    org.billing_period = body.billing_period or org.billing_period
    await db.commit()
    await db.refresh(org)

    return {
        "plan": org.plan,
        "subscription_status": org.subscription_status,
        "paypal_subscription_id": org.paypal_subscription_id,
        "billing_period": org.billing_period,
        "next_billing_date": _next_billing_date(subscription),
    }


@router.post("/cancel")
async def cancel_billing(
    body: CancelBillingRequest | None = None,
    org: Organization = Depends(get_current_org_from_jwt),
    db: AsyncSession = Depends(get_db),
):
    if org.paypal_subscription_id:
        try:
            paypal_client.cancel_subscription(
                org.paypal_subscription_id,
                (body.reason if body else "Customer requested cancellation"),
            )
        except (PayPalError, httpx.HTTPError) as exc:
            raise _paypal_error(exc) from exc

    org.subscription_status = "cancelled"
    await db.commit()
    await db.refresh(org)
    return {"success": True, "subscription_status": org.subscription_status}


@router.get("/status")
async def billing_status(org: Organization = Depends(get_current_org_from_jwt)):
    subscription = None
    if org.paypal_subscription_id:
        try:
            subscription = paypal_client.get_subscription(org.paypal_subscription_id)
        except (PayPalError, httpx.HTTPError):
            subscription = None

    return {
        "plan": org.plan,
        "subscription_status": org.subscription_status,
        "paypal_subscription_id": org.paypal_subscription_id,
        "billing_period": org.billing_period,
        "next_billing_date": _next_billing_date(subscription),
    }
