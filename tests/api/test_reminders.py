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
        assert "Is that okay" in greeting.text and "Priya" in greeting.text
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
    body = emails[0].get_content()
    assert "medical alert" in body and "We tried to call Mom twice" in body
    assert "Morning pills" not in body and "Morning pills" not in emails[0]["Subject"]

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
    body = emails[0].get_content()
    assert "Nobody marked it as taken" in body and "tried to call" not in body
    assert "tap Taken" in body and body.rstrip().endswith("FollowThrough Health")


def test_missed_email_explains_calls_waiting_for_agreement(calls):
    # The person never pressed 1 on the first call, so no reminder call went out.
    _, emails = calls
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        client.post(
            "/reminders",
            json=reminder_body(
                times=[(now - timedelta(minutes=1)).strftime("%H:%M")], call=True, phone="+15551234567",
                consent_confirmed=True, alert_on_miss=True,
            ),
            headers=headers,
        )
    with SessionLocal() as db:
        reminder_routes.run_dispatch(db, now)
        assert reminder_routes.run_dispatch(db, now + timedelta(minutes=61))["missed"] == 1
        dose = db.scalars(select(ReminderEvent).where(ReminderEvent.kind == "dose")).one()
        assert dose.attempts == 0  # only the "press 1 to agree" call went out
    body = emails[0].get_content()
    assert "has not yet pressed 1" in body and "tried to call" not in body


def test_friendly_clock():
    assert reminder_routes.friendly_clock(datetime(2026, 1, 1, 0, 5)) == "12:05 AM"
    assert reminder_routes.friendly_clock(datetime(2026, 1, 1, 8, 0)) == "8:00 AM"
    assert reminder_routes.friendly_clock(datetime(2026, 1, 1, 12, 30)) == "12:30 PM"
    assert reminder_routes.friendly_clock(datetime(2026, 1, 1, 20, 45)) == "8:45 PM"


@pytest.mark.parametrize("language", ["en", "es"])
def test_call_scripts_are_clear_for_an_older_listener(language):
    from app.services import reminder_calls

    lines = reminder_calls.SCRIPTS[language]
    for key in ("consent", "dose"):
        text = reminder_calls.script(language, key, "Priya")
        assert "FollowThrough Health" in text and "Priya" in text
        assert ("press 9" if language == "en" else "marque 9") in text
        assert ("press 2" if language == "en" else "marque 2") in text
    assert ("press 9" if language == "en" else "marque 9") in lines["consent_yes"]
    # Never a medicine name, dose or amount: only "your medicine".
    for text in lines.values():
        assert not any(word in text.lower() for word in ("mg", "pill", "tablet", "dose", "dosis", "pastilla"))
    assert all(len(sentence.split()) <= 16 for text in lines.values() for sentence in text.split(". "))

    body = reminder_calls.gather_twiml(language, reminder_calls.script(language, "dose"), "https://api.test/a")
    assert body.index('<Pause length="1"/>') < body.index("<Gather")
    assert 'timeout="10"' in body and '<prosody rate="90%">' in body


def test_other_people_cannot_see_or_change_my_reminders():
    with TestClient(create_app()) as client:
        owner, _ = auth_headers(client)
        other, _ = auth_headers(client)
        reminder = client.post("/reminders", json=reminder_body(), headers=owner).json()
        rid = reminder["id"]
        assert client.get("/reminders", headers=other).json() == []
        assert client.put(f"/reminders/{rid}", json=reminder_body(label="Changed"), headers=other).status_code == 404
        assert client.post(f"/reminders/{rid}/taken", json={"time": "08:00"}, headers=other).status_code == 404
        assert client.post(f"/reminders/{rid}/consent-call", json={}, headers=other).status_code in (404, 422)
        assert client.delete(f"/reminders/{rid}", headers=other).status_code == 404
        # Still there and unchanged for the owner.
        mine = client.get("/reminders", headers=owner).json()
        assert [item["label"] for item in mine] == ["Morning pills"]


def test_failed_twilio_call_is_counted_as_a_failure_not_a_call(calls, monkeypatch):
    placed, emails = calls

    def refuse(to, url):
        raise OSError("provider unavailable")

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        client.post(
            "/reminders",
            json=reminder_body(
                times=[(now - timedelta(minutes=1)).strftime("%H:%M")], call=True, phone="+15551234567",
                consent_confirmed=True,
            ),
            headers=headers,
        )
    monkeypatch.setattr(reminder_routes.reminder_calls, "place_call", refuse)
    with SessionLocal() as db:
        counts = reminder_routes.run_dispatch(db, now)
    assert counts["calls"] == 1 and counts["call_failures"] == 1


def dose_events_for(db, reminder_id):
    return db.scalars(
        select(ReminderEvent).where(ReminderEvent.reminder_id == reminder_id, ReminderEvent.kind == "dose")
    ).all()


@pytest.mark.parametrize(
    ("clock", "start", "local_expected"),
    [
        # Clocks go back at 2:00 on 1 Nov 2026 in New York, so 1:30 happens twice: remind once.
        ("01:30", datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc), "01:30"),
        # Clocks jump from 2:00 to 3:00 on 8 Mar 2026, so 2:30 never happens: remind once, at 3:30.
        ("02:30", datetime(2026, 3, 8, 5, 0, tzinfo=timezone.utc), "03:30"),
    ],
)
def test_daylight_saving_days_give_exactly_one_reminder(calls, clock, start, local_expected):
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        created = client.post(
            "/reminders", json=reminder_body(times=[clock], timezone="America/New_York"), headers=headers
        ).json()
    with SessionLocal() as db:
        # Run the 5-minute scheduler through the whole night.
        for step in range(0, 6 * 12):
            reminder_routes.run_dispatch(db, start + timedelta(minutes=5 * step))
        events = dose_events_for(db, created["id"])
        assert len(events) == 1
        local = reminder_routes.as_utc(events[0].due_at).astimezone(reminder_routes.zone("America/New_York"))
        assert local.strftime("%H:%M") == local_expected


def test_reminder_follows_its_own_time_zone_not_the_server(calls):
    # 08:00 in Tokyo is 23:00 UTC the day before; the scheduler runs in UTC.
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        created = client.post(
            "/reminders", json=reminder_body(times=["08:00"], timezone="Asia/Tokyo"), headers=headers
        ).json()
    with SessionLocal() as db:
        reminder_routes.run_dispatch(db, datetime(2026, 6, 1, 22, 55, tzinfo=timezone.utc))
        assert dose_events_for(db, created["id"]) == []
        reminder_routes.run_dispatch(db, datetime(2026, 6, 1, 23, 0, tzinfo=timezone.utc))
        reminder_routes.run_dispatch(db, datetime(2026, 6, 1, 23, 5, tzinfo=timezone.utc))
        events = dose_events_for(db, created["id"])
        assert len(events) == 1
        assert reminder_routes.as_utc(events[0].due_at) == datetime(2026, 6, 1, 23, 0, tzinfo=timezone.utc)
