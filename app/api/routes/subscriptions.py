import json
import urllib.error
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, status
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
