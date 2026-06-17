from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import storage


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


def test_text_file_upload_is_extracted_for_analysis_when_form_text_is_empty():
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)

        upload = client.post(
            "/reports/upload-file",
            data={"patient_id": patient_id},
            files={
                "file": (
                    "ldl-report.txt",
                    b"LDL cholesterol elevated. A1C normal. No chest pain.",
                    "text/plain",
                )
            },
            headers=headers,
        )
        assert upload.status_code == 200

        analysis = client.post(f"/reports/{upload.json()['id']}/analyze", headers=headers)
        assert analysis.status_code == 200
        analysis_payload = analysis.json()
        assert analysis_payload["risk_level"] == "clinician_review"
        assert "heart_support" in analysis_payload["summary"]["detected_terms"]


def test_unreadable_file_upload_requests_ocr_text_before_analysis():
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)

        upload = client.post(
            "/reports/upload-file",
            data={"patient_id": patient_id},
            files={"file": ("scan.pdf", b"%PDF-1.4 fake scan", "application/pdf")},
            headers=headers,
        )
        assert upload.status_code == 200

        analysis = client.post(f"/reports/{upload.json()['id']}/analyze", headers=headers)
        assert analysis.status_code == 200
        analysis_payload = analysis.json()
        assert analysis_payload["risk_level"] == "needs_text"
        assert analysis_payload["status"] == "needs_readable_text"
        assert "no readable text" in analysis_payload["summary"]["message"]


def test_report_text_can_be_added_after_file_upload_and_then_analyzed():
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)

        upload = client.post(
            "/reports/upload-file",
            data={"patient_id": patient_id},
            files={"file": ("scan.pdf", b"%PDF-1.4 fake scan", "application/pdf")},
            headers=headers,
        )
        assert upload.status_code == 200

        first_analysis = client.post(f"/reports/{upload.json()['id']}/analyze", headers=headers)
        assert first_analysis.status_code == 200
        assert first_analysis.json()["status"] == "needs_readable_text"

        update = client.put(
            f"/reports/{upload.json()['id']}/text",
            json={"report_text": "LDL cholesterol elevated. A1C normal. No chest pain."},
            headers=headers,
        )
        assert update.status_code == 200
        assert update.json()["status"] == "uploaded"

        second_analysis = client.post(f"/reports/{upload.json()['id']}/analyze", headers=headers)
        assert second_analysis.status_code == 200
        analysis_payload = second_analysis.json()
        assert analysis_payload["risk_level"] == "clinician_review"
        assert "heart_support" in analysis_payload["summary"]["detected_terms"]


def test_image_upload_uses_ocr_text_for_analysis_when_extractor_is_available(monkeypatch):
    monkeypatch.setattr(
        storage,
        "extract_text_with_openai_vision",
        lambda temp_path, content_type: "LDL cholesterol elevated. A1C normal. No chest pain.",
    )
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)

        upload = client.post(
            "/reports/upload-file",
            data={"patient_id": patient_id},
            files={"file": ("report.png", b"fake-image-bytes", "image/png")},
            headers=headers,
        )
        assert upload.status_code == 200

        analysis = client.post(f"/reports/{upload.json()['id']}/analyze", headers=headers)
        assert analysis.status_code == 200
        analysis_payload = analysis.json()
        assert analysis_payload["risk_level"] == "clinician_review"
        assert "heart_support" in analysis_payload["summary"]["detected_terms"]


def test_image_upload_without_ocr_key_requests_readable_text():
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)

        upload = client.post(
            "/reports/upload-file",
            data={"patient_id": patient_id},
            files={"file": ("report.png", b"fake-image-bytes", "image/png")},
            headers=headers,
        )
        assert upload.status_code == 200

        analysis = client.post(f"/reports/{upload.json()['id']}/analyze", headers=headers)
        assert analysis.status_code == 200
        analysis_payload = analysis.json()
        assert analysis_payload["risk_level"] == "needs_text"
        assert analysis_payload["status"] == "needs_readable_text"


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

        owner_report = client.post(
            "/reports/upload",
            json={
                "patient_id": owner_patient_id,
                "file_name": "owner-report.txt",
                "content_type": "text/plain",
                "report_text": "Blood pressure report",
            },
            headers=owner_headers,
        )
        assert owner_report.status_code == 200

        blocked_text_update = client.put(
            f"/reports/{owner_report.json()['id']}/text",
            json={"report_text": "LDL elevated"},
            headers=other_headers,
        )
        assert blocked_text_update.status_code == 403
