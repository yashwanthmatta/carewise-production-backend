from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.rbac import Role, require_roles
from app.core.security import CurrentUser
from app.db.session import get_db
from app.models.carewise import Subscription
from app.schemas.carewise import SubscriptionCheckoutIn, SubscriptionCheckoutOut
from app.services.audit import write_audit

router = APIRouter()


@router.post("/checkout", response_model=SubscriptionCheckoutOut)
def create_checkout(
    payload: SubscriptionCheckoutIn,
    user: CurrentUser = Depends(require_roles(Role.PATIENT, Role.ADMIN)),
    db: Session = Depends(get_db),
):
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
        checkout_url=f"https://payments.example.com/carewise/{subscription.id}",
    )
