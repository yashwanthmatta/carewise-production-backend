"""People, repeat use and paid plans for the founder summary (22 Nov 2026).

Only counts are returned: no emails, names, report content or ids. Accounts that are not
customers are left out and counted separately, so the numbers describe real people:
- test accounts on reserved domains (example.com/.org/.net, *.test, *.invalid, *.example), which
  is what the nightly smoke test and every automated test use, and any address starting "smoke-";
- staff accounts (any role other than patient).
Revenue is not stored here (Stripe holds it), so it is reported as unknown, never estimated.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.carewise import PatientProfile, ReportUpload, Subscription, User
from app.services.entitlements import CURRENT_STATUSES

RESERVED_TEST_DOMAINS = ("example.com", "example.org", "example.net")
RESERVED_TEST_SUFFIXES = (".test", ".invalid", ".example", ".localhost")


def is_test_or_staff(email: str, role: str) -> bool:
    address = (email or "").strip().lower()
    local, _, domain = address.partition("@")
    if role != "patient":
        return True
    if local.startswith("smoke-"):
        return True
    return domain in RESERVED_TEST_DOMAINS or domain.endswith(RESERVED_TEST_SUFFIXES)


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def people_metrics(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    users = db.execute(select(User.id, User.email, User.role, User.created_at)).all()
    customers = {
        user_id: _aware(created)
        for user_id, email, role, created in users
        if not is_test_or_staff(email, role)
    }
    excluded = len(users) - len(customers)

    report_days: dict[str, set] = {}
    rows = db.execute(
        select(PatientProfile.user_id, ReportUpload.created_at).join(
            PatientProfile, ReportUpload.patient_id == PatientProfile.id
        )
    ).all()
    for user_id, created in rows:
        if user_id in customers and created is not None:
            report_days.setdefault(user_id, set()).add(_aware(created).date())

    paid: dict[str, int] = {}
    for user_id, plan_code, status in db.execute(
        select(Subscription.user_id, Subscription.plan_code, Subscription.status)
    ).all():
        if user_id in customers and status in CURRENT_STATUSES and plan_code != "basic":
            paid[plan_code] = paid.get(plan_code, 0) + 1

    def joined_since(days: int) -> int:
        cutoff = now - timedelta(days=days)
        return sum(1 for created in customers.values() if created and created >= cutoff)

    return {
        "people": {
            "customer_accounts": len(customers),
            "new_last_7_days": joined_since(7),
            "new_last_30_days": joined_since(30),
            "excluded_test_or_staff_accounts": excluded,
            "with_a_saved_report": len(report_days),
            "saved_reports_on_two_or_more_days": sum(
                1 for days in report_days.values() if len(days) >= 2
            ),
        },
        "paid": {
            "active_paid_subscriptions": sum(paid.values()),
            "by_plan": paid,
            "revenue": None,
            "revenue_note": "Not stored by FollowThrough; Stripe's dashboard is the source of truth.",
        },
    }
