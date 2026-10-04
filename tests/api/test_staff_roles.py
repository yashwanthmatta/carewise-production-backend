from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import User
from tests.api.test_reports_and_access_control import auth_headers, create_profile

PASSWORD = "change-me-long-password"


def test_public_signup_cannot_create_admin_or_clinician(monkeypatch):
    monkeypatch.setattr(settings, "staff_emails", "")
    with TestClient(create_app()) as client:
        for role in ("admin", "clinician", "superuser"):
            response = client.post("/auth/signup", json={"email": f"{role}@example.com", "password": PASSWORD, "role": role})
            assert response.status_code == 403
        assert client.post("/auth/signup", json={"email": "p@example.com", "password": PASSWORD, "role": "patient"}).status_code == 200


def test_listed_staff_can_sign_up_with_their_role(monkeypatch):
    monkeypatch.setattr(settings, "staff_emails", "doc@clinic.org:clinician, Boss@CareWise.app:admin")
    with TestClient(create_app()) as client:
        doctor = client.post("/auth/signup", json={"email": "doc@clinic.org", "password": PASSWORD, "role": "clinician"})
        assert doctor.status_code == 200
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {doctor.json()['access_token']}"})
        assert me.json()["role"] == "clinician"
        # Listed as clinician, so admin is still refused.
        assert client.post("/auth/signup", json={"email": "boss@carewise.app", "password": PASSWORD, "role": "clinician"}).status_code == 403
        assert client.post("/auth/signup", json={"email": "boss@carewise.app", "password": PASSWORD, "role": "admin"}).status_code == 200


def test_existing_unlisted_staff_account_acts_as_patient(monkeypatch):
    monkeypatch.setattr(settings, "staff_emails", "")
    with TestClient(create_app()) as client:
        patient_headers, _ = auth_headers(client)
        patient_id = create_profile(client, patient_headers)
        sneaky = client.post("/auth/signup", json={"email": "sneaky@example.com", "password": PASSWORD, "role": "patient"})
        # Simulate an account that got an elevated role before this fix.
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == "sneaky@example.com"))
            user.role = "admin"
            db.commit()
        headers = {"Authorization": f"Bearer {sneaky.json()['access_token']}"}
        assert client.get("/auth/me", headers=headers).json()["role"] == "patient"
        assert client.get("/admin/summary", headers=headers).status_code == 403
        assert client.get(f"/lab-trends?patient_id={patient_id}", headers=headers).status_code == 403
        with SessionLocal() as db:
            assert db.scalar(select(User).where(User.email == "sneaky@example.com")).role == "patient"
