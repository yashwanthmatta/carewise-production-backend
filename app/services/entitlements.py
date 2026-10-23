"""One answer to "what can this account use?", whichever store the plan was bought in.

Plans can come from Stripe (website), Apple, Google or a clinic contract; all of them
are rows in `subscriptions`, so web, iPhone and Android read the same entitlement.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.carewise import Subscription

# Paid statuses that still count as the person's current plan (past_due is a grace period).
CURRENT_STATUSES = ("active", "past_due")

PLAN_RANK = {"basic": 0, "plus": 1, "premium": 2}

# Never behind a paywall: understanding a report, what to tell the doctor, and
# anything about urgency or safety.
ALWAYS_FREE = frozenset({
    "report_explanations",
    "doctor_brief",
    "safety_messages",
    "health_record",
    "appointment_questions",
})

# Candidates for paid plans. Nothing is locked until the owner turns on
# entitlement_enforcement after choosing what each plan includes.
PLAN_FEATURES = {
    "basic": frozenset(),
    "plus": frozenset({"long_term_trends", "advanced_reminders", "report_organization", "cross_device_reports"}),
    "premium": frozenset({
        "long_term_trends", "advanced_reminders", "report_organization", "cross_device_reports",
        "family_profiles", "caregiver_sharing", "shared_calendar",
    }),
}

ALL_FEATURES = ALWAYS_FREE | frozenset().union(*PLAN_FEATURES.values())


def is_current(subscription: Subscription, now: datetime | None = None) -> bool:
    if subscription.status not in CURRENT_STATUSES:
        return False
    if subscription.expires_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    expires_at = subscription.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > now


def current_subscriptions(db: Session, user_id: str) -> list[Subscription]:
    rows = db.scalars(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status.in_(CURRENT_STATUSES))
        .order_by(Subscription.created_at.desc())
    ).all()
    return [row for row in rows if is_current(row)]


def best_subscription(db: Session, user_id: str) -> Subscription | None:
    """The highest current plan across every provider (newest wins a tie)."""
    best = None
    for row in current_subscriptions(db, user_id):
        if best is None or PLAN_RANK.get(row.plan_code, 0) > PLAN_RANK.get(best.plan_code, 0):
            best = row
    return best


def entitlements_for(db: Session, user_id: str) -> dict:
    subscription = best_subscription(db, user_id)
    plan_code = subscription.plan_code if subscription and subscription.plan_code in PLAN_FEATURES else "basic"
    enforced = settings.entitlement_enforcement
    features = ALL_FEATURES if not enforced else ALWAYS_FREE | PLAN_FEATURES[plan_code]
    return {
        "plan_code": plan_code,
        "source": subscription.payment_provider if subscription else "free",
        "status": subscription.status if subscription else "free",
        "expires_at": subscription.expires_at if subscription else None,
        "enforced": enforced,
        "features": sorted(features),
    }


def has_feature(db: Session, user_id: str, feature: str) -> bool:
    if feature in ALWAYS_FREE or not settings.entitlement_enforcement:
        return True
    return feature in entitlements_for(db, user_id)["features"]
