import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.api.routes import subscriptions
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.carewise import Subscription
from tests.api.test_reports_and_access_control import auth_headers


def test_subscription_plans_are_public_and_structured():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/subscriptions/plans")
        assert response.status_code == 200
        plans = response.json()
        assert [plan["plan_code"] for plan in plans] == ["basic", "plus", "premium"]
        assert plans[0]["monthly_price_usd"] == 29
        assert plans[0]["features"]


def test_subscription_checkout_uses_known_plan():
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        response = client.post(
            "/subscriptions/checkout",
            json={"plan_code": "plus", "payment_provider": "manual"},
            headers=headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["plan_code"] == "plus"
        assert "/plus/" in payload["checkout_url"]


def test_subscription_checkout_uses_stripe_when_enabled(monkeypatch):
    monkeypatch.setattr(subscriptions, "stripe_enabled", lambda: True)
    monkeypatch.setattr(
        subscriptions,
        "create_stripe_checkout_session",
        lambda plan, subscription_id, customer_email: {
            "id": "cs_test_carewise",
            "url": "https://checkout.stripe.com/c/pay/cs_test_carewise",
        },
    )
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        response = client.post(
            "/subscriptions/checkout",
            json={"plan_code": "premium", "payment_provider": "manual"},
            headers=headers,
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["checkout_url"].startswith("https://checkout.stripe.com/")


def test_stripe_webhook_activates_checkout_subscription(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test_secret")
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        response = client.post(
            "/subscriptions/checkout",
            json={"plan_code": "plus", "payment_provider": "manual"},
            headers=headers,
        )
        subscription_id = response.json()["id"]

        payload = {
            "id": "evt_checkout_completed",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_carewise",
                    "client_reference_id": subscription_id,
                    "subscription": "sub_test_carewise",
                    "payment_status": "paid",
                    "metadata": {"subscription_id": subscription_id, "plan_code": "plus"},
                }
            },
        }
        webhook_response = client.post(
            "/subscriptions/webhook",
            content=json.dumps(payload),
            headers={"Stripe-Signature": stripe_signature(payload, "whsec_test_secret")},
        )
        assert webhook_response.status_code == 200
        assert webhook_response.json()["status"] == "active"

        with SessionLocal() as db:
            subscription = db.scalar(select(Subscription).where(Subscription.id == subscription_id))
            assert subscription is not None
            assert subscription.status == "active"
            assert subscription.provider_reference == "sub_test_carewise"


def test_stripe_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test_secret")
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/subscriptions/webhook",
            content=json.dumps({"type": "checkout.session.completed", "data": {"object": {}}}),
            headers={"Stripe-Signature": "t=123,v1=bad"},
        )
        assert response.status_code == 400


def stripe_signature(payload: dict, secret: str) -> str:
    timestamp = int(time.time())
    body = json.dumps(payload)
    digest = hmac.new(secret.encode("utf-8"), f"{timestamp}.{body}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"
