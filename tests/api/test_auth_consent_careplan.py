from fastapi.testclient import TestClient

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
    headers = {"Authorization": f"Bearer {token}"}

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


def test_password_reset_request_does_not_reveal_unknown_email():
    app = create_app()
    client = TestClient(app)

    response = client.post("/auth/password-reset/request", json={"email": "missing@example.com"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["reset_token"] == ""
