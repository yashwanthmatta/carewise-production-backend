from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app


def test_auth_consent_profile_and_care_plan_flow():
    """Integration-test target for the FastAPI app once dependencies/PostgreSQL are available."""
    app = create_app()
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200

    signup = client.post(
        "/auth/signup",
        json={"email": "patient@example.com", "password": "change-me-long-password", "role": "patient"},
    )
    assert signup.status_code in {200, 201}
    token = signup.json()["access_token"]
    assert signup.json()["refresh_token"]
    headers = {"Authorization": f"Bearer {token}"}

    session = client.get("/auth/me", headers=headers)
    assert session.status_code == 200
    assert session.json()["email"] == "patient@example.com"
    assert session.json()["role"] == "patient"

    consent = client.post(
        "/consent",
        json={"version": "2026-06-15", "accepted": True, "region": "US-CA"},
        headers=headers,
    )
    assert consent.status_code == 200

    profile = client.put(
        "/patients/me/profile",
        json={
            "name": "Demo Patient",
            "date_of_birth": "1990-01-01",
            "sex_at_birth": "female",
            "conditions": "High blood pressure",
            "allergies": "None",
            "location_region": "US-CA",
            "insurance_status": "some",
        },
        headers=headers,
    )
    assert profile.status_code == 200
    patient_id = profile.json()["patient_id"]

    plan = client.post(
        "/care-plans/generate",
        json={
            "patient_id": patient_id,
            "symptom_text": "I need blood pressure diet help. No chest pain or trouble breathing.",
            "goals": ["Diet plan"],
            "diet_style": "flexible",
            "activity_level": "light",
        },
        headers=headers,
    )
    assert plan.status_code == 200
    assert plan.json()["risk_level"] in {"routine", "clinician_review", "emergency"}


def test_password_reset_flow_updates_password_and_prevents_reuse():
    app = create_app()
    client = TestClient(app)

    signup = client.post(
        "/auth/signup",
        json={"email": "reset@example.com", "password": "old-password-long", "role": "patient"},
    )
    assert signup.status_code == 200

    request = client.post("/auth/password-reset/request", json={"email": "reset@example.com"})
    assert request.status_code == 200
    reset_token = request.json()["reset_token"]
    assert reset_token

    confirm = client.post(
        "/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "new-password-long"},
    )
    assert confirm.status_code == 200
    assert confirm.json()["access_token"]

    old_login = client.post(
        "/auth/login",
        json={"email": "reset@example.com", "password": "old-password-long"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        json={"email": "reset@example.com", "password": "new-password-long"},
    )
    assert new_login.status_code == 200

    reused = client.post(
        "/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "another-password-long"},
    )
    assert reused.status_code == 400


def test_auth_me_requires_valid_token():
    app = create_app()
    client = TestClient(app)

    missing = client.get("/auth/me")
    assert missing.status_code == 401

    invalid = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert invalid.status_code == 401


def test_password_reset_request_does_not_reveal_unknown_email():
    app = create_app()
    client = TestClient(app)

    response = client.post("/auth/password-reset/request", json={"email": "missing@example.com"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["reset_token"] == ""


def test_password_reset_queues_email_when_smtp_is_configured(monkeypatch):
    sent_messages = []
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_username", "carewise")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    monkeypatch.setattr(settings, "smtp_from_email", "support@example.com")
    monkeypatch.setattr(
        "app.services.email_delivery.send_password_reset_email",
        lambda to_email, reset_token: sent_messages.append((to_email, reset_token)),
    )
    app = create_app()
    client = TestClient(app)

    signup = client.post(
        "/auth/signup",
        json={"email": "email-reset@example.com", "password": "old-password-long", "role": "patient"},
    )
    assert signup.status_code == 200

    response = client.post("/auth/password-reset/request", json={"email": "email-reset@example.com"})
    assert response.status_code == 200
    assert response.json()["delivery_status"] == "email_queued"
    assert response.json()["reset_token"]
    assert sent_messages
    assert sent_messages[0][0] == "email-reset@example.com"

    missing = client.post("/auth/password-reset/request", json={"email": "unknown-reset@example.com"})
    assert missing.status_code == 200
    assert missing.json()["delivery_status"] == "email_queued"
    assert missing.json()["reset_token"] == ""


def test_login_rate_limit_blocks_repeated_attempts(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", 2)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 900)
    app = create_app()
    client = TestClient(app)

    for _ in range(2):
        response = client.post(
            "/auth/login",
            json={"email": "rate@example.com", "password": "wrong-password-long"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/auth/login",
        json={"email": "rate@example.com", "password": "wrong-password-long"},
    )
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"]


def test_refresh_token_rotates_and_logout_revokes():
    app = create_app()
    client = TestClient(app)

    signup = client.post(
        "/auth/signup",
        json={"email": "refresh@example.com", "password": "old-password-long", "role": "patient"},
    )
    assert signup.status_code == 200
    first_refresh_token = signup.json()["refresh_token"]
    assert first_refresh_token

    refresh = client.post("/auth/refresh", json={"refresh_token": first_refresh_token})
    assert refresh.status_code == 200
    second_refresh_token = refresh.json()["refresh_token"]
    assert second_refresh_token
    assert second_refresh_token != first_refresh_token

    reused = client.post("/auth/refresh", json={"refresh_token": first_refresh_token})
    assert reused.status_code == 401

    logout = client.post("/auth/logout", json={"refresh_token": second_refresh_token})
    assert logout.status_code == 200

    revoked = client.post("/auth/refresh", json={"refresh_token": second_refresh_token})
    assert revoked.status_code == 401


def test_password_reset_request_rate_limit_blocks_repeated_attempts(monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_max_attempts", 1)
    monkeypatch.setattr(settings, "auth_rate_limit_window_seconds", 900)
    app = create_app()
    client = TestClient(app)

    first = client.post("/auth/password-reset/request", json={"email": "missing-rate@example.com"})
    assert first.status_code == 200

    blocked = client.post("/auth/password-reset/request", json={"email": "missing-rate@example.com"})
    assert blocked.status_code == 429
