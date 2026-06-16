from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def auth_headers(client: TestClient, role: str = "patient") -> tuple[dict[str, str], str]:
    email = f"{role}-{uuid4().hex}@example.com"
    signup = client.post(
        "/auth/signup",
        json={"email": email, "password": "change-me-long-password", "role": role},
    )
    assert signup.status_code == 200
    return {"Authorization": f"Bearer {signup.json()['access_token']}"}, email


def create_profile(client: TestClient, headers: dict[str, str], name: str = "Test Patient") -> str:
    response = client.put(
        "/patients/me/profile",
        json={
            "name": name,
            "date_of_birth": "1990-01-01",
            "sex_at_birth": "female",
            "conditions": "High blood pressure",
            "allergies": "None",
            "location_region": "US-CA",
            "insurance_status": "some",
        },
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["patient_id"]


def test_report_file_upload_and_analysis_flow():
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)

        upload = client.post(
            "/reports/upload-file",
            data={
                "patient_id": patient_id,
                "report_text": "Blood pressure 142/92. LDL elevated. No chest pain.",
            },
            files={"file": ("bp-report.txt", b"Blood pressure 142/92", "text/plain")},
            headers=headers,
        )
        assert upload.status_code == 200
        upload_payload = upload.json()
        assert upload_payload["id"].startswith("report_")
        assert upload_payload["storage_url"].startswith("local://reports/")
        assert upload_payload["file_size_bytes"] > 0

        analysis = client.post(f"/reports/{upload_payload['id']}/analyze", headers=headers)
        assert analysis.status_code == 200
        analysis_payload = analysis.json()
        assert analysis_payload["report_id"] == upload_payload["id"]
        assert analysis_payload["risk_level"] in {"routine", "clinician_review", "emergency"}
        assert analysis_payload["summary"]["message"].endswith("This is not a diagnosis.")


def test_patient_cannot_access_another_patient_records():
    app = create_app()
    with TestClient(app) as client:
        owner_headers, _ = auth_headers(client)
        other_headers, _ = auth_headers(client)
        owner_patient_id = create_profile(client, owner_headers, "Owner Patient")
        create_profile(client, other_headers, "Other Patient")

        medication = client.post(
            f"/patients/{owner_patient_id}/medications",
            json={"name": "Lisinopril", "dose": "10 mg"},
            headers=other_headers,
        )
        assert medication.status_code == 403

        care_plan = client.post(
            "/care-plans/generate",
            json={
                "patient_id": owner_patient_id,
                "symptom_text": "I need blood pressure diet help. No chest pain.",
                "goals": ["Diet plan"],
                "diet_style": "flexible",
                "activity_level": "light",
            },
            headers=other_headers,
        )
        assert care_plan.status_code == 403

        report = client.post(
            "/reports/upload",
            json={
                "patient_id": owner_patient_id,
                "file_name": "owner-report.txt",
                "content_type": "text/plain",
                "report_text": "Blood pressure report",
            },
            headers=other_headers,
        )
        assert report.status_code == 403
