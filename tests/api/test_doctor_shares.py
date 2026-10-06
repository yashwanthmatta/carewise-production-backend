from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import DoctorShare
from tests.api.test_reports_and_access_control import auth_headers

SNAPSHOT = {"person": "Mom", "score": 72, "findings": [{"label": "LDL cholesterol", "level": "Needs attention"}]}


def test_family_can_share_and_doctor_can_view_without_account():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        created = client.post("/shares", json={"snapshot": SNAPSHOT, "label": "For Dr. Patel", "days": 7}, headers=headers)
        assert created.status_code == 200
        token = created.json()["token"]
        assert created.json()["label"] == "For Dr. Patel"

        view = client.post("/shares/view", json={"token": token})
        assert view.status_code == 200
        assert view.json()["snapshot"]["person"] == "Mom"

        listed = client.get("/shares", headers=headers).json()
        assert listed[0]["view_count"] == 1
        assert "token" not in listed[0]

    with SessionLocal() as db:
        share = db.scalars(select(DoctorShare)).one()
        assert token not in share.token_hash
        assert "Mom" not in share.encrypted_snapshot


def test_turned_off_or_expired_links_stop_working():
    with TestClient(create_app()) as client:
        headers, _ = auth_headers(client)
        first = client.post("/shares", json={"snapshot": SNAPSHOT}, headers=headers).json()
        assert client.post(f"/shares/{first['id']}/revoke", headers=headers).json()["revoked"] is True
        assert client.post("/shares/view", json={"token": first["token"]}).status_code == 404

        second = client.post("/shares", json={"snapshot": SNAPSHOT, "days": 1}, headers=headers).json()
        with SessionLocal() as db:
            share = db.get(DoctorShare, second["id"])
            share.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
        assert client.post("/shares/view", json={"token": second["token"]}).status_code == 404
        assert client.post("/shares/view", json={"token": "x" * 40}).status_code == 404


def test_sharing_needs_an_account_and_limits_size_and_days():
    with TestClient(create_app()) as client:
        assert client.post("/shares", json={"snapshot": SNAPSHOT}).status_code == 401
        headers, _ = auth_headers(client)
        assert client.post("/shares", json={"snapshot": SNAPSHOT, "days": 90}, headers=headers).status_code == 422
        big = {"text": "x" * 70_000}
        assert client.post("/shares", json={"snapshot": big}, headers=headers).status_code == 413


def test_other_people_cannot_turn_off_my_link():
    with TestClient(create_app()) as client:
        mine, _ = auth_headers(client)
        share = client.post("/shares", json={"snapshot": SNAPSHOT}, headers=mine).json()
        theirs, _ = auth_headers(client)
        assert client.post(f"/shares/{share['id']}/revoke", headers=theirs).status_code == 404
