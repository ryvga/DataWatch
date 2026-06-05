import time
from typing import Any

import httpx

from app.config import settings


class PayPalError(RuntimeError):
    """Raised when PayPal returns an unusable response."""


class PayPalClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.client_id = client_id if client_id is not None else settings.PAYPAL_CLIENT_ID
        self.client_secret = client_secret if client_secret is not None else settings.PAYPAL_CLIENT_SECRET
        self.base_url = (base_url if base_url is not None else settings.PAYPAL_BASE_URL).rstrip("/")
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)

    def get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        if not self.client_id or not self.client_secret:
            raise PayPalError("PayPal client credentials are not configured")

        response = self._client.post(
            "/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise PayPalError("PayPal token response did not include access_token")

        expires_in = int(payload.get("expires_in", 3600))
        self._access_token = token
        self._token_expires_at = time.time() + expires_in
        return token

    def create_order(
        self,
        amount_usd: float,
        description: str,
        return_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "description": description,
                    "custom_id": description[:127],
                    "amount": {
                        "currency_code": "USD",
                        "value": f"{amount_usd:.2f}",
                    },
                }
            ],
            "application_context": {
                "return_url": return_url,
                "cancel_url": cancel_url,
                "user_action": "PAY_NOW",
            },
        }
        data = self._post("/v2/checkout/orders", payload)
        return {"id": self._require_id(data), "approval_url": self._approval_url(data)}

    def capture_order(self, order_id: str) -> dict[str, Any]:
        return self._post(f"/v2/checkout/orders/{order_id}/capture", {})

    def create_subscription_plan(self, name: str, price_usd: float, interval: str) -> str:
        product = self._post(
            "/v1/catalogs/products",
            {
                "name": name,
                "description": "DataWatch recurring billing product",
                "type": "SERVICE",
                "category": "SOFTWARE",
            },
        )
        interval_unit = interval.upper()
        if interval_unit not in {"MONTH", "YEAR"}:
            raise ValueError("interval must be MONTH or YEAR")

        plan = self._post(
            "/v1/billing/plans",
            {
                "product_id": self._require_id(product),
                "name": name,
                "status": "ACTIVE",
                "billing_cycles": [
                    {
                        "frequency": {"interval_unit": interval_unit, "interval_count": 1},
                        "tenure_type": "REGULAR",
                        "sequence": 1,
                        "total_cycles": 0,
                        "pricing_scheme": {
                            "fixed_price": {
                                "value": f"{price_usd:.2f}",
                                "currency_code": "USD",
                            }
                        },
                    }
                ],
                "payment_preferences": {
                    "auto_bill_outstanding": True,
                    "setup_fee_failure_action": "CONTINUE",
                    "payment_failure_threshold": 3,
                },
            },
        )
        return self._require_id(plan)

    def create_subscription(self, plan_id: str, return_url: str, cancel_url: str) -> dict[str, str]:
        data = self._post(
            "/v1/billing/subscriptions",
            {
                "plan_id": plan_id,
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                    "user_action": "SUBSCRIBE_NOW",
                },
            },
        )
        return {"id": self._require_id(data), "approval_url": self._approval_url(data)}

    def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        return self._get(f"/v1/billing/subscriptions/{subscription_id}")

    def cancel_subscription(self, subscription_id: str, reason: str) -> bool:
        response = self._client.post(
            f"/v1/billing/subscriptions/{subscription_id}/cancel",
            headers=self._headers(),
            json={"reason": reason},
        )
        response.raise_for_status()
        return True

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get(self, path: str) -> dict[str, Any]:
        response = self._client.get(path, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(path, headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _require_id(payload: dict[str, Any]) -> str:
        paypal_id = payload.get("id")
        if not paypal_id:
            raise PayPalError("PayPal response did not include id")
        return paypal_id

    @staticmethod
    def _approval_url(payload: dict[str, Any]) -> str:
        for link in payload.get("links", []):
            if link.get("rel") in {"approve", "approval_url"} and link.get("href"):
                return link["href"]
        raise PayPalError("PayPal response did not include approval URL")


paypal_client = PayPalClient()
