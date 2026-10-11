import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import reminders as reminder_routes
from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import MedicineReminder, ReminderEvent
from tests.api.test_reports_and_access_control import auth_headers

API = "https://api.test"


@pytest.fixture
def calls(monkeypatch):
    placed = []
    emails = []
    monkeypatch.setattr(settings, "twilio_account_sid", "AC123")
    monkeypatch.setattr(settings, "twilio_auth_token", "twilio-secret")
    monkeypatch.setattr(settings, "twilio_from_number", "+15550000000")
    monkeypatch.setattr(settings, "public_api_url", API)
    monkeypatch.setattr(settings, "reminder_cron_token", "cron-secret")
    monkeypatch.setattr(type(settings), "email_delivery_enabled", property(lambda self: True))
    monkeypatch.setattr(reminder_routes.reminder_calls, "place_call", lambda to, url: placed.append((to, url)) or "CA1")
    monkeypatch.setattr(reminder_routes, "send_email", lambda message: emails.append(message))
    return placed, emails


def signed_post(client, path, params):
    payload = API + path + "".join(f"{key}{params[key]}" for key in sorted(params))
    signature = base64.b64encode(hmac.new(b"twilio-secret", payload.encode(), hashlib.sha1).digest()).decode()
    return client.post(path, data=params, headers={"X-Twilio-Signature": signature})


def reminder_body(**extra):
    body = {"person": "Mom", "label": "Morning pills", "times": ["08:00"], "timezone": "UTC"}
    body.update(extra)
    return body


def test_family_sets_a_reminder_and_marks_it_taken():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        created = client.post("/reminders", json=reminder_body(times=["20:00", "08:00"]), headers=headers)
        assert created.status_code == 200
        reminder = created.json()
        assert reminder["times"] == ["08:00", "20:00"]
        assert reminder["call_status"] == "off"
        assert [dose["time"] for dose in reminder["today"]] == ["08:00", "20:00"]

        taken = client.post(f"/reminders/{reminder['id']}/taken", json={"time": "08:00"}, headers=headers)
        assert taken.json()["today"][0]["status"] == "taken"
        assert client.get("/reminders", headers=headers).json()[0]["today"][0]["status"] == "taken"

        bad = client.post("/reminders", json=reminder_body(times=["8am"]), headers=headers)
        assert bad.status_code == 422

    with SessionLocal() as db:
        stored = db.scalars(select(MedicineReminder)).one()
        assert "Mom" not in stored.encrypted_person
        assert "Morning" not in stored.encrypted_label


def test_calls_need_a_valid_number_and_the_persons_agreement():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        no_consent = client.post("/reminders", json=reminder_body(call=True, phone="+1 555 123 4567"), headers=headers)
        assert no_consent.status_code == 422
        bad_phone = client.post("/reminders", json=reminder_body(call=True, phone="555", consent_confirmed=True), headers=headers)
        assert bad_phone.status_code == 422
        ok = client.post(
            "/reminders",
            json=reminder_body(call=True, phone="+1 (555) 123-4567", consent_confirmed=True, caller_name="Priya"),
            headers=headers,
        )
        assert ok.status_code == 200
        assert ok.json()["call_status"] == "pending_consent"
        assert ok.json()["phone_last4"] == "4567"
        # Editing without retyping the number keeps it and does not ask for agreement again.
        edited = client.put(
            f"/reminders/{ok.json()['id']}", json=reminder_body(call=True, times=["09:00"], caller_name="Priya"), headers=headers
        )
        assert edited.status_code == 200
        assert edited.json()["phone_last4"] == "4567" and edited.json()["times"] == ["09:00"]


def test_consent_call_then_reminder_call_then_missed_email(calls):
    placed, emails = calls
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    due = now - timedelta(minutes=2)
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        created = client.post(
            "/reminders",
            json=reminder_body(
                times=[due.strftime("%H:%M")], call=True, phone="+15551234567",
                consent_confirmed=True, caller_name="Priya", alert_on_miss=True,
            ),
            headers=headers,
        ).json()

        # The first call only asks for agreement; no reminder call before "1".
        assert client.post("/reminders/dispatch", headers={"X-CareWise-Cron-Token": "cron-secret"}).json()["calls"] == 1
        consent_url = placed[0][1]
        path = consent_url.removeprefix(API)
        greeting = signed_post(client, path, {"CallSid": "CA1"})
        assert "agree" in greeting.text and "Priya" in greeting.text
        assert "Morning pills" not in greeting.text
        assert signed_post(client, path + "/answer", {"Digits": "1"}).status_code == 200
        assert client.get("/reminders", headers=headers).json()[0]["call_status"] == "active"

        assert client.post(f"{path}/answer", data={"Digits": "1"}).status_code == 403

    with SessionLocal() as db:
        first = reminder_routes.run_dispatch(db, now)
        assert first["calls"] == 1
        dose_path = placed[-1][1].removeprefix(API)
        assert reminder_routes.run_dispatch(db, now + timedelta(minutes=5))["calls"] == 0
        assert reminder_routes.run_dispatch(db, now + timedelta(minutes=11))["calls"] == 1
        assert reminder_routes.run_dispatch(db, now + timedelta(minutes=27))["missed"] == 1
        event = db.scalars(select(ReminderEvent).where(ReminderEvent.kind == "dose")).one()
        assert event.status == "missed" and event.alerted_at is not None
    assert len(emails) == 1 and "Mom" in emails[0]["Subject"]
    assert "medical alert" in emails[0].get_content()

    with TestClient(create_app()) as client:
        answer = signed_post(client, dose_path, {"CallSid": "CA2"})
        assert "time for your medicine" in answer.text
        assert "turned off" in signed_post(client, dose_path + "/answer", {"Digits": "9"}).text
    with SessionLocal() as db:
        assert db.get(MedicineReminder, created["id"]).call_status == "stopped"


def test_dispatch_needs_the_cron_token(calls):
    with TestClient(create_app()) as client:
        assert client.post("/reminders/dispatch").status_code == 403
        assert client.post("/reminders/dispatch", headers={"X-CareWise-Cron-Token": "wrong"}).status_code == 403


def test_app_only_reminder_is_marked_missed_after_an_hour(calls):
    placed, emails = calls
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        client.post(
            "/reminders", json=reminder_body(times=[(now - timedelta(minutes=1)).strftime("%H:%M")], alert_on_miss=True),
            headers=headers,
        )
    with SessionLocal() as db:
        assert reminder_routes.run_dispatch(db, now)["created"] == 1
        assert reminder_routes.run_dispatch(db, now + timedelta(minutes=30))["missed"] == 0
        assert reminder_routes.run_dispatch(db, now + timedelta(minutes=61))["missed"] == 1
    assert placed == [] and len(emails) == 1
