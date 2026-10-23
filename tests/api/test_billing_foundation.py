"""Shared entitlements and safe Stripe event handling (no live charges)."""

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import BillingEvent, Subscription, User
from app.services import entitlements
from tests.api.test_reports_and_access_control import auth_headers
from tests.api.test_subscriptions import stripe_signature

SECRET = "whsec_test_secret"


def send(client, event_id, event_type, obj):
    payload = {"id": event_id, "type": event_type, "data": {"object": obj}}
    return client.post(
        "/subscriptions/webhook",
        content=json.dumps(payload),
        headers={"Stripe-Signature": stripe_signature(payload, SECRET)},
    )


def paid_plus(client, headers):
    """Create a Plus checkout and complete it, as Stripe would."""
    sub_id = client.post("/subscriptions/checkout", json={"plan_code": "plus", "payment_provider": "manual"}, headers=headers).json()["id"]
    response = send(client, f"evt_done_{sub_id}", "checkout.session.completed", {
        "id": "cs_test", "client_reference_id": sub_id, "subscription": f"sub_stripe_{sub_id}", "payment_status": "paid",
    })
    assert response.json()["status"] == "active"
    return sub_id, f"sub_stripe_{sub_id}"


def status_of(sub_id):
    with SessionLocal() as db:
        return db.get(Subscription, sub_id).status


def test_entitlements_default_to_every_feature_while_locks_are_off():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        body = client.get("/subscriptions/entitlements", headers=headers).json()
        assert body["plan_code"] == "basic"
        assert body["enforced"] is False
        assert set(body["features"]) == set(entitlements.ALL_FEATURES)


def test_safety_features_are_free_on_every_plan_even_with_locks_on(monkeypatch):
    monkeypatch.setattr(settings, "entitlement_enforcement", True)
    for plan, features in entitlements.PLAN_FEATURES.items():
        assert not (features & entitlements.ALWAYS_FREE), plan
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        body = client.get("/subscriptions/entitlements", headers=headers).json()
        assert body["enforced"] is True
        assert set(body["features"]) == set(entitlements.ALWAYS_FREE)
        assert {"report_explanations", "doctor_brief", "safety_messages"} <= set(body["features"])


def test_paid_plan_unlocks_its_features_when_locks_are_on(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "entitlement_enforcement", True)
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        paid_plus(client, headers)
        body = client.get("/subscriptions/entitlements", headers=headers).json()
        assert body["plan_code"] == "plus" and body["source"] == "stripe"
        assert "long_term_trends" in body["features"]
        assert "family_profiles" not in body["features"]


def test_a_retried_stripe_event_is_applied_once(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        sub_id, stripe_sub = paid_plus(client, headers)
        first = send(client, "evt_fail_1", "invoice.payment_failed", {"id": "in_1", "subscription": stripe_sub})
        assert first.json()["status"] == "past_due"
        send(client, "evt_paid_1", "invoice.paid", {"id": "in_1", "subscription": stripe_sub})
        assert status_of(sub_id) == "active"
        # Stripe re-delivers the old failure: it must not knock the plan back to past_due.
        again = send(client, "evt_fail_1", "invoice.payment_failed", {"id": "in_1", "subscription": stripe_sub})
        assert again.json()["duplicate"] is True
        assert status_of(sub_id) == "active"
        with SessionLocal() as db:
            assert len(db.scalars(select(BillingEvent).where(BillingEvent.event_id == "evt_fail_1")).all()) == 1


def test_renewal_and_cancellation_follow_stripe_subscription_status(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        sub_id, stripe_sub = paid_plus(client, headers)
        send(client, "evt_u1", "customer.subscription.updated", {"id": stripe_sub, "status": "unpaid"})
        assert status_of(sub_id) == "past_due"
        # Newer Stripe API versions nest the subscription id on invoices.
        send(client, "evt_p1", "invoice.paid", {"id": "in_2", "parent": {"subscription_details": {"subscription": stripe_sub}}})
        assert status_of(sub_id) == "active"
        send(client, "evt_u2", "customer.subscription.updated", {"id": stripe_sub, "status": "canceled"})
        assert status_of(sub_id) == "cancelled"
        # A late invoice event never brings a cancelled plan back.
        send(client, "evt_p2", "invoice.paid", {"id": "in_3", "subscription": stripe_sub})
        assert status_of(sub_id) == "cancelled"
        assert client.get("/subscriptions/me", headers=headers).json()["plan_code"] == "basic"


def test_one_paid_plan_per_account(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        paid_plus(client, headers)
        second = client.post("/subscriptions/checkout", json={"plan_code": "premium", "payment_provider": "manual"}, headers=headers)
        assert second.status_code == 409
        assert "Manage plan" in second.json()["detail"]


def test_store_subscriptions_end_on_their_expiry_date():
    with TestClient(create_app()) as client:
        headers, email = auth_headers(client)
        with SessionLocal() as db:
            user_id = db.scalar(select(User.id).where(User.email == email))
            db.add(Subscription(user_id=user_id, plan_code="premium", status="active", payment_provider="apple",
                                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
            db.add(Subscription(user_id=user_id, plan_code="plus", status="active", payment_provider="google",
                                expires_at=datetime.now(timezone.utc) + timedelta(days=20)))
            db.commit()
        body = client.get("/subscriptions/entitlements", headers=headers).json()
        # The expired Apple Family plan no longer counts; the live Google Plus plan does.
        assert body["plan_code"] == "plus" and body["source"] == "google"
