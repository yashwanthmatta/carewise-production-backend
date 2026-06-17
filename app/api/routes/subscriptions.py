from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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
        "summary": "Education summaries, reminders, and local care plan export.",
        "features": ["Report summaries", "Diet reminders", "Local care plan export"],
    },
    "plus": {
        "plan_code": "plus",
        "name": "Plus",
        "monthly_price_usd": 79,
        "summary": "Care planning, insurance guidance, and monthly review workflow.",
        "features": ["Care plan sync", "Insurance guidance", "Monthly review workflow"],
    },
    "premium": {
        "plan_code": "premium",
        "name": "Premium",
        "monthly_price_usd": 149,
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
        payment_provider=payload.payment_provider,
        provider_reference="prototype_checkout",
    )
    db.add(subscription)
    db.flush()
    write_audit(db, user.user_id, "", "subscription_checkout_created", "subscription", subscription.id, {"plan": payload.plan_code})
    db.commit()
    return SubscriptionCheckoutOut(
        id=subscription.id,
        plan_code=subscription.plan_code,
        status=subscription.status,
        checkout_url=f"https://payments.example.com/carewise/{plan['plan_code']}/{subscription.id}",
    )
