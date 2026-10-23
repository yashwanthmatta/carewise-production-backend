import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import BillingEvent, Subscription
from app.schemas.carewise import (
    BillingPortalOut,
    EntitlementsOut,
    SubscriptionCheckoutIn,
    SubscriptionCheckoutOut,
    SubscriptionMeOut,
    SubscriptionPlanOut,
)
from app.services.audit import write_audit
from app.services.entitlements import PLAN_RANK, best_subscription, entitlements_for

router = APIRouter()

# Plan codes stay stable (stored on subscriptions); names and prices follow the
# public pricing: Free, Plus $7 and Family $12 a month. Starting prices to test.
SUBSCRIPTION_PLANS = {
    "basic": {
        "plan_code": "basic",
        "name": "Free",
        "monthly_price_usd": 0,
        "stripe_lookup_key": "",
        "summary": "Explain any report, take a doctor brief, keep a health record.",
        "features": ["Explain any lab or scan report", "One-page doctor brief", "Lifetime health record"],
    },
    "plus": {
        "plan_code": "plus",
        "name": "Plus",
        "monthly_price_usd": 7,
        "stripe_lookup_key": "carewise_plus_monthly",
        "summary": "Personal plans, reminders and trends over the years.",
        "features": ["Personal plan from your own results", "Reminders", "Trends over the years"],
    },
    "premium": {
        "plan_code": "premium",
        "name": "Family",
        "monthly_price_usd": 12,
        "stripe_lookup_key": "carewise_family_monthly",
        "summary": "Everything in Plus for up to 5 people, shared with caregivers.",
        "features": ["Everything in Plus", "Up to 5 family members", "Shared with siblings and caregivers"],
    },
}


@router.get("/plans", response_model=list[SubscriptionPlanOut])
def list_subscription_plans():
    return [SubscriptionPlanOut(**plan) for plan in SUBSCRIPTION_PLANS.values()]


def current_subscription(db: Session, user_id: str) -> Subscription | None:
    return best_subscription(db, user_id)


@router.get("/entitlements", response_model=EntitlementsOut)
def my_entitlements(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    """What this account can use on every device, whichever store the plan came from."""
    return EntitlementsOut(**entitlements_for(db, user.user_id))


@router.get("/me", response_model=SubscriptionMeOut)
def my_subscription(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    subscription = current_subscription(db, user.user_id)
    plan = SUBSCRIPTION_PLANS.get(subscription.plan_code if subscription else "basic", SUBSCRIPTION_PLANS["basic"])
    return SubscriptionMeOut(
        plan_code=plan["plan_code"],
        plan_name=plan["name"],
        status=subscription.status if subscription else "free",
        payments_enabled=stripe_enabled(),
        can_manage_billing=bool(stripe_enabled() and subscription and subscription.provider_customer),
    )


@router.post("/portal", response_model=BillingPortalOut)
def billing_portal(
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    subscription = current_subscription(db, user.user_id)
    if not stripe_enabled() or subscription is None or not subscription.provider_customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No paid plan to manage yet.")
    portal_url = create_stripe_portal_session(subscription.provider_customer)
    write_audit(db, user.user_id, "", "subscription_portal_opened", "subscription", subscription.id, {})
    db.commit()
    return BillingPortalOut(portal_url=portal_url)


@router.post("/checkout", response_model=SubscriptionCheckoutOut)
def create_checkout(
    payload: SubscriptionCheckoutIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    plan = SUBSCRIPTION_PLANS.get(payload.plan_code)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown subscription plan.")
    if not plan["monthly_price_usd"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The Free plan needs no payment.")
    existing = current_subscription(db, user.user_id)
    if existing is not None and PLAN_RANK.get(existing.plan_code, 0) > 0:
        # One paid plan per account; changes go through Manage plan so nobody pays twice.
        name = SUBSCRIPTION_PLANS.get(existing.plan_code, {}).get("name", "a paid plan")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have {name}. Use Manage plan to change or cancel it.",
        )
    subscription = Subscription(
        user_id=user.user_id,
        plan_code=payload.plan_code,
        status="pending",
        payment_provider="stripe" if stripe_enabled() else payload.payment_provider,
        provider_reference="pending",
    )
    db.add(subscription)
    db.flush()
    checkout_url = manual_checkout_url(plan, subscription.id)
    if stripe_enabled():
        checkout = create_stripe_checkout_session(plan, subscription.id, user.email)
        checkout_url = checkout["url"]
        subscription.provider_reference = checkout["id"]
    else:
        subscription.provider_reference = "prototype_checkout"
    write_audit(db, user.user_id, "", "subscription_checkout_created", "subscription", subscription.id, {"plan": payload.plan_code})
    db.commit()
    return SubscriptionCheckoutOut(
        id=subscription.id,
        plan_code=subscription.plan_code,
        status=subscription.status,
        checkout_url=checkout_url,
    )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    webhook_secret = settings.clean_env_value(settings.stripe_webhook_secret)
    if not webhook_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe webhook is not configured.")

    body = await request.body()
    verify_stripe_signature(body, stripe_signature, webhook_secret)
    try:
        event = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook JSON.") from exc

    event_type = event.get("type", "")
    event_object = event.get("data", {}).get("object", {})
    if not isinstance(event_object, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload.")

    # Stripe retries deliveries; apply each event once.
    event_id = event.get("id")
    if isinstance(event_id, str) and event_id:
        if db.scalar(select(BillingEvent).where(BillingEvent.provider == "stripe", BillingEvent.event_id == event_id)):
            return {"received": True, "updated": False, "duplicate": True}

    subscription = subscription_for_stripe_object(db, event_object)
    if isinstance(event_id, str) and event_id:
        db.add(BillingEvent(provider="stripe", event_id=event_id, event_type=event_type, subscription_id=subscription.id if subscription else ""))
    if subscription is None:
        commit_billing_event(db)
        return {"received": True, "updated": False}

    new_status = subscription_status_for_event(event_type, event_object)
    if new_status and not (subscription.status == "cancelled" and event_type.startswith("invoice.")):
        # A late invoice event never brings back a cancelled plan.
        subscription.status = new_status
        # A verified Stripe event means Stripe is where this plan is billed.
        subscription.payment_provider = "stripe"

    provider_subscription_id = stripe_subscription_ref(event_object) or event_object.get("id")
    if isinstance(provider_subscription_id, str) and provider_subscription_id.startswith("sub_"):
        subscription.provider_reference = provider_subscription_id
    customer_id = event_object.get("customer")
    if isinstance(customer_id, str) and customer_id.startswith("cus_"):
        subscription.provider_customer = customer_id

    write_audit(
        db,
        subscription.user_id,
        "",
        "subscription_webhook_received",
        "subscription",
        subscription.id,
        {"provider": "stripe", "event_type": event_type, "status": subscription.status},
    )
    if not commit_billing_event(db):
        return {"received": True, "updated": False, "duplicate": True}
    return {"received": True, "updated": True, "status": subscription.status}


def commit_billing_event(db: Session) -> bool:
    """Commit, treating a concurrent delivery of the same event as already applied."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


def stripe_enabled() -> bool:
    return bool(settings.clean_env_value(settings.stripe_secret_key))


def manual_checkout_url(plan: dict, subscription_id: str) -> str:
    return f"https://payments.example.com/carewise/{plan['plan_code']}/{subscription_id}"


def stripe_post(path: str, data: dict) -> dict:
    request = urllib.request.Request(
        f"https://api.stripe.com/v1/{path}",
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.clean_env_value(settings.stripe_secret_key)}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe could not be reached.") from exc


def create_stripe_portal_session(customer_id: str) -> str:
    payload = stripe_post("billing_portal/sessions", {"customer": customer_id, "return_url": settings.frontend_url})
    portal_url = payload.get("url")
    if not portal_url:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Stripe billing page response was incomplete.")
    return portal_url


def create_stripe_checkout_session(plan: dict, subscription_id: str, customer_email: str) -> dict:
    data = {
        "mode": "subscription",
        "customer_email": customer_email,
        "client_reference_id": subscription_id,
        "success_url": settings.stripe_success_url,
        "cancel_url": settings.stripe_cancel_url,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][unit_amount]": str(int(plan["monthly_price_usd"]) * 100),
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][product_data][name]": f"FollowThrough Health {plan['name']}",
        "line_items[0][price_data][product_data][metadata][plan_code]": plan["plan_code"],
        "metadata[subscription_id]": subscription_id,
        "metadata[plan_code]": plan["plan_code"],
    }
    request = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.clean_env_value(settings.stripe_secret_key)}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe checkout session could not be created.",
        ) from exc

    session_id = payload.get("id")
    checkout_url = payload.get("url")
    if not session_id or not checkout_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe checkout session response was incomplete.",
        )
    return {"id": session_id, "url": checkout_url}


def verify_stripe_signature(body: bytes, signature_header: str, webhook_secret: str, tolerance_seconds: int = 300) -> None:
    timestamp = ""
    signatures = []
    for part in signature_header.split(","):
        key, _, value = part.partition("=")
        if key == "t":
            timestamp = value
        if key == "v1":
            signatures.append(value)
    if not timestamp or not signatures:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature.")

    try:
        timestamp_int = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature timestamp.") from exc

    if abs(int(time.time()) - timestamp_int) > tolerance_seconds:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Expired Stripe signature.")

    signed_payload = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe signature.")


def stripe_subscription_ref(event_object: dict) -> str:
    """The Stripe subscription id on an event object (newer API versions nest it on invoices)."""
    ref = event_object.get("subscription")
    if isinstance(ref, str) and ref:
        return ref
    details = (event_object.get("parent") or {}).get("subscription_details") or {}
    ref = details.get("subscription") if isinstance(details, dict) else ""
    return ref if isinstance(ref, str) else ""


def subscription_for_stripe_object(db: Session, event_object: dict) -> Subscription | None:
    subscription_id = event_object.get("client_reference_id") or event_object.get("metadata", {}).get("subscription_id")
    if isinstance(subscription_id, str) and subscription_id.startswith("sub_"):
        subscription = db.get(Subscription, subscription_id)
        if subscription is not None:
            return subscription

    provider_reference = stripe_subscription_ref(event_object) or event_object.get("id")
    if isinstance(provider_reference, str) and provider_reference:
        return db.scalar(select(Subscription).where(Subscription.provider_reference == provider_reference))
    return None


# Stripe subscription statuses mapped onto ours (customer.subscription.updated).
STRIPE_SUBSCRIPTION_STATUSES = {
    "active": "active",
    "trialing": "active",
    "past_due": "past_due",
    "unpaid": "past_due",
    "canceled": "cancelled",
    "incomplete_expired": "cancelled",
    "paused": "cancelled",
}


def subscription_status_for_event(event_type: str, event_object: dict) -> str:
    if event_type == "checkout.session.completed":
        payment_status = event_object.get("payment_status", "")
        return "active" if payment_status in {"paid", "no_payment_required"} else "pending"
    if event_type == "invoice.payment_failed":
        return "past_due"
    if event_type in {"invoice.paid", "invoice.payment_succeeded"}:
        # Renewal, or a failed payment that was later paid.
        return "active"
    if event_type == "customer.subscription.updated":
        return STRIPE_SUBSCRIPTION_STATUSES.get(event_object.get("status", ""), "")
    if event_type == "customer.subscription.deleted":
        return "cancelled"
    return ""
