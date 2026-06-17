import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import Subscription
from app.schemas.carewise import SubscriptionCheckoutIn, SubscriptionCheckoutOut, SubscriptionPlanOut
from app.services.audit import write_audit

router = APIRouter()

SUBSCRIPTION_PLANS = {
    "basic": {
        "plan_code": "basic",
        "name": "Basic",
        "monthly_price_usd": 29,
        "stripe_lookup_key": "carewise_basic_monthly",
        "summary": "Education summaries, reminders, and local care plan export.",
        "features": ["Report summaries", "Diet reminders", "Local care plan export"],
    },
    "plus": {
        "plan_code": "plus",
        "name": "Plus",
        "monthly_price_usd": 79,
        "stripe_lookup_key": "carewise_plus_monthly",
        "summary": "Care planning, insurance guidance, and monthly review workflow.",
        "features": ["Care plan sync", "Insurance guidance", "Monthly review workflow"],
    },
    "premium": {
        "plan_code": "premium",
        "name": "Premium",
        "monthly_price_usd": 149,
        "stripe_lookup_key": "carewise_premium_monthly",
        "summary": "Priority navigation, weekly coaching workflow, and concierge handoff.",
        "features": ["Priority matching", "Weekly coaching workflow", "Concierge handoff"],
    },
}


@router.get("/plans", response_model=list[SubscriptionPlanOut])
def list_subscription_plans():
    return [SubscriptionPlanOut(**plan) for plan in SUBSCRIPTION_PLANS.values()]


@router.post("/checkout", response_model=SubscriptionCheckoutOut)
def create_checkout(
    payload: SubscriptionCheckoutIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    plan = SUBSCRIPTION_PLANS.get(payload.plan_code)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown subscription plan.")
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

    subscription = subscription_for_stripe_object(db, event_object)
    if subscription is None:
        return {"received": True, "updated": False}

    new_status = subscription_status_for_event(event_type, event_object)
    if new_status:
        subscription.status = new_status

    provider_subscription_id = event_object.get("subscription") or event_object.get("id")
    if isinstance(provider_subscription_id, str) and provider_subscription_id.startswith("sub_"):
        subscription.provider_reference = provider_subscription_id

    write_audit(
        db,
        subscription.user_id,
        "",
        "subscription_webhook_received",
        "subscription",
        subscription.id,
        {"provider": "stripe", "event_type": event_type, "status": subscription.status},
    )
    db.commit()
    return {"received": True, "updated": True, "status": subscription.status}


def stripe_enabled() -> bool:
    return bool(settings.clean_env_value(settings.stripe_secret_key))


def manual_checkout_url(plan: dict, subscription_id: str) -> str:
    return f"https://payments.example.com/carewise/{plan['plan_code']}/{subscription_id}"


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
        "line_items[0][price_data][product_data][name]": f"CareWise {plan['name']}",
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


def subscription_for_stripe_object(db: Session, event_object: dict) -> Subscription | None:
    subscription_id = event_object.get("client_reference_id") or event_object.get("metadata", {}).get("subscription_id")
    if isinstance(subscription_id, str) and subscription_id.startswith("sub_"):
        subscription = db.get(Subscription, subscription_id)
        if subscription is not None:
            return subscription

    provider_reference = event_object.get("subscription") or event_object.get("id")
    if isinstance(provider_reference, str) and provider_reference:
        return db.scalar(select(Subscription).where(Subscription.provider_reference == provider_reference))
    return None


def subscription_status_for_event(event_type: str, event_object: dict) -> str:
    if event_type == "checkout.session.completed":
        payment_status = event_object.get("payment_status", "")
        return "active" if payment_status in {"paid", "no_payment_required"} else "pending"
    if event_type == "invoice.payment_failed":
        return "past_due"
    if event_type == "customer.subscription.deleted":
        return "cancelled"
    return ""
