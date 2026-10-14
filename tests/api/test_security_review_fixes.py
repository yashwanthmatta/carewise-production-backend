# Fixes for the independent security review of 2026-10-14.
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import RefreshToken, User
from app.services.rate_limit import client_address
from tests.api.test_email_intake import clinic_with_owner, intake, raw_email  # noqa: F401 - intake is an autouse fixture

PASSWORD = "change-me-long-password"


def test_emailed_labs_with_a_generic_subject_never_share_a_patient_code():
    with TestClient(create_app()) as client:
        headers, email, clinic = clinic_with_owner(client)
        for subject in ("DEID lab results", "DEID lab results", "DEID", "DEID A1C results", "DEID Vitamin B12", "DEID CMP-14", "DEID labs 10/14", "DEID results Oct 2026", "DEID LDL-100", "DEID Oct-2026", "DEID JD-1042"):
            client.post("/inbound/email/intake-secret", content=raw_email(email, clinic["intake_address"], subject=subject), headers={"Content-Type": "message/rfc822"})
        client.post("/inbound/email/intake-secret", content=raw_email(email, clinic["intake_address"], subject="Fwd: DEID REF-2201"), headers={"Content-Type": "message/rfc822"})
        refs = [p["patient_ref"] for p in client.get(f"/clinics/{clinic['id']}/packets", headers=headers).json()]
        assert "REF-2201" in refs and "lab" not in refs
        generic = [r for r in refs if r != "REF-2201"]
        assert len(generic) == 11 and len(set(generic)) == 11 and all(r.startswith("EMAIL-") for r in generic)


class FakeRequest:
    def __init__(self, forwarded, host="10.0.0.5"):
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}
        self.client = type("C", (), {"host": host})()


def test_client_address_ignores_what_the_browser_puts_first():
    assert client_address(FakeRequest("1.2.3.4, 93.184.216.34")) == "93.184.216.34"
    assert client_address(FakeRequest("1.2.3.4, 93.184.216.34, 10.1.2.3")) == "93.184.216.34"
    assert client_address(FakeRequest("")) == "10.0.0.5"


def test_login_guesses_are_limited_per_account_even_from_many_addresses(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", 1000)
    with TestClient(create_app()) as client:
        email = f"guess-{uuid4().hex}@example.com"
        client.post("/auth/signup", json={"email": email, "password": PASSWORD, "role": "patient"})
        codes = []
        for i in range(22):
            response = client.post("/auth/login", json={"email": email, "password": "wrong-password-xx"}, headers={"X-Forwarded-For": f"198.51.100.{i}"})
            codes.append(response.status_code)
        assert codes[:20] == [401] * 20 and codes[-1] == 429


def test_password_reset_signs_out_every_other_session():
    with TestClient(create_app()) as client:
        email = f"reset-{uuid4().hex}@example.com"
        old = client.post("/auth/signup", json={"email": email, "password": PASSWORD, "role": "patient"}).json()
        token = client.post("/auth/password-reset/request", json={"email": email}).json()["reset_token"]
        assert client.post("/auth/password-reset/confirm", json={"token": token, "new_password": "brand-new-password-1"}).status_code == 200
        assert client.post("/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        statuses = [t.status for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))]
        assert "revoked" in statuses and statuses.count("active") == 1  # only the session the reset itself started
