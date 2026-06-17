from fastapi.testclient import TestClient

from app.main import create_app
from app.api.routes import subscriptions
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
