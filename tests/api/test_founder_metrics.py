"""Founder summary: real-people counts (22 Nov 2026). Synthetic accounts only. Checks that test and
staff accounts are left out, repeat use means saved reports on two or more different days, paid
plans are counted, revenue is never estimated, and no email or content is returned."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import ReportUpload, Subscription, User
from app.services.founder_metrics import is_test_or_staff

TOKEN = {"X-Founder-Token": "founder-secret-value"}


def signup(client, email):
    response = client.post(
        "/auth/signup",
        json={"email": email, "password": "change-me-long-password", "role": "patient"},
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    profile = client.put(
        "/patients/me/profile",
        json={
            "name": "Synthetic",
            "date_of_birth": "1950-02-02",
            "sex_at_birth": "female",
            "conditions": "",
            "allergies": "None",
            "location_region": "US-CA",
            "insurance_status": "some",
        },
        headers=headers,
    )
    return headers, profile.json()["patient_id"]


def upload(client, headers, patient_id):
    response = client.post(
        "/reports/upload",
        json={
            "patient_id": patient_id,
            "file_name": "synthetic.txt",
            "content_type": "text/plain",
            "report_text": "Potassium 4.2 mmol/L 3.5-5.1",
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_test_domains_smoke_and_staff_are_not_customers():
    assert is_test_or_staff("smoke-1732000000@example.com", "patient")
    assert is_test_or_staff("person@example.org", "patient")
    assert is_test_or_staff("qa@clinic.test", "patient")
    assert is_test_or_staff("doc@realclinic.org", "clinician")
    assert not is_test_or_staff("someone@gmail.com", "patient")


def test_founder_summary_counts_real_people_only(monkeypatch):
    monkeypatch.setattr(settings, "founder_token", "founder-secret-value")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with TestClient(create_app()) as client:
        a_headers, a_patient = signup(client, "carer.one@fastmail.com")
        b_headers, b_patient = signup(client, "carer.two@fastmail.com")
        smoke_headers, smoke_patient = signup(client, "smoke-1732000000@example.com")
        first = upload(client, a_headers, a_patient)
        upload(client, a_headers, a_patient)
        upload(client, b_headers, b_patient)
        upload(client, smoke_headers, smoke_patient)
        with SessionLocal() as db:
            # Carer one's first report was 40 days ago: saved reports on two different days.
            report = db.get(ReportUpload, first)
            report.created_at = datetime.now(timezone.utc) - timedelta(days=40)
            user_b = db.scalar(select(User).where(User.email == "carer.two@fastmail.com"))
            db.add(Subscription(user_id=user_b.id, plan_code="plus", status="active"))
            db.commit()
        body = client.get("/product/summary", headers=TOKEN).json()

    people = body["people"]
    assert people["customer_accounts"] == 2 and people["excluded_test_or_staff_accounts"] == 1
    assert people["new_last_7_days"] == 2
    assert people["with_a_saved_report"] == 2 and people["saved_reports_on_two_or_more_days"] == 1
    assert body["paid"]["active_paid_subscriptions"] == 1 and body["paid"]["by_plan"] == {"plus": 1}
    assert body["paid"]["revenue"] is None and "Stripe" in body["paid"]["revenue_note"]
    assert body["ai"]["state"] == "not_configured"
    text = str({k: body[k] for k in ("people", "paid", "ai")})
    assert "fastmail" not in text and "Potassium" not in text
