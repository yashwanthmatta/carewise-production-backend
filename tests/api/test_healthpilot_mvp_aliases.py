from fastapi.testclient import TestClient

from app.main import create_app


def test_healthpilot_mvp_aliases_work():
    app = create_app()
    with TestClient(app) as client:
        signup = client.post(
            "/signup",
            json={"email": "healthpilot@example.com", "password": "change-me-long-password", "role": "patient"},
        )
        assert signup.status_code == 200
        headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}

        profile = client.put(
            "/patients/me/profile",
            json={
                "name": "HealthPilot Patient",
                "date_of_birth": "1990-01-01",
                "sex_at_birth": "unknown",
                "conditions": "High LDL",
                "allergies": "None",
                "location_region": "US",
                "insurance_status": "some",
            },
            headers=headers,
        )
        assert profile.status_code == 200
        patient_id = profile.json()["patient_id"]

        upload = client.post(
            "/upload-report",
            data={
                "patient_id": patient_id,
                "report_text": "LDL cholesterol elevated. A1C normal. No chest pain.",
            },
            files={"file": ("blood-report.txt", b"LDL cholesterol elevated.", "text/plain")},
            headers=headers,
        )
        assert upload.status_code == 200
        report_id = upload.json()["id"]

        analysis = client.post("/analyze-report", json={"report_id": report_id}, headers=headers)
        assert analysis.status_code == 200
        assert analysis.json()["summary"]["message"] == "Report education summary generated. This is not a diagnosis."

        results = client.get(f"/report-results?patient_id={patient_id}", headers=headers)
        assert results.status_code == 200
        assert len(results.json()) == 1

        user_profile = client.get("/user-profile", headers=headers)
        assert user_profile.status_code == 200
        assert user_profile.json()["profile"]["name"] == "HealthPilot Patient"
