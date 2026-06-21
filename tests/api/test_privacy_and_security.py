from fastapi.testclient import TestClient

from app.main import create_app
from app.api.routes import health
from tests.api.test_reports_and_access_control import auth_headers, create_profile


def test_security_headers_are_applied():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"


def test_ready_endpoint_checks_dependencies():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ready"
        assert payload["checks"]["database"] is True
        assert payload["checks"]["configuration"] is True
        assert payload["checks"]["storage"] is True


def test_ready_endpoint_returns_503_when_dependency_fails(monkeypatch):
    monkeypatch.setattr(health, "database_ready", lambda: False)
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["detail"]["status"] == "not_ready"
        assert response.json()["detail"]["checks"]["database"] is False


def test_features_endpoint_reports_capabilities_without_secrets():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/features")
        assert response.status_code == 200
        payload = response.json()
        assert payload["report_uploads"] is True
        assert payload["text_extraction"] is True
        assert payload["pdf_text_extraction"] is True
        assert isinstance(payload["stripe_checkout"], bool)
        assert "api_key" not in payload
        assert "secret" not in payload


def test_privacy_export_delete_request_and_delete_flow():
    app = create_app()
    with TestClient(app) as client:
        headers, email = auth_headers(client)
        patient_id = create_profile(client, headers)

        consent = client.post(
            "/consent",
            json={"version": "2026-06-16", "accepted": True, "region": "US"},
            headers=headers,
        )
        assert consent.status_code == 200

        report = client.post(
            "/reports/upload",
            json={
                "patient_id": patient_id,
                "file_name": "export-report.txt",
                "content_type": "text/plain",
                "report_text": "Blood pressure follow up",
            },
            headers=headers,
        )
        assert report.status_code == 200

        analysis = client.post(f"/reports/{report.json()['id']}/analyze", headers=headers)
        assert analysis.status_code == 200

        medication = client.post(
            f"/patients/{patient_id}/medications",
            json={"name": "Metformin", "dose": "500 mg", "timing": "Morning", "notes": "Export test"},
            headers=headers,
        )
        assert medication.status_code == 200

        care_plan = client.post(
            "/care-plans/generate",
            json={
                "patient_id": patient_id,
                "symptom_text": "I need help preparing questions for high blood pressure. No chest pain.",
                "goals": ["Doctor visit preparation"],
                "diet_style": "vegetarian",
                "activity_level": "light",
            },
            headers=headers,
        )
        assert care_plan.status_code == 200

        summary = client.get("/privacy/me/export-summary", headers=headers)
        assert summary.status_code == 200
        summary_payload = summary.json()
        assert summary_payload["account"]["email"] == email
        assert summary_payload["counts"]["patients"] == 1
        assert summary_payload["counts"]["reports"] == 1
        assert summary_payload["counts"]["report_analyses"] == 1
        assert summary_payload["counts"]["medications"] == 1
        assert summary_payload["counts"]["intakes"] == 1
        assert summary_payload["counts"]["care_plans"] == 1
        assert summary_payload["includes_private_storage_urls"] is False
        assert "patients" not in summary_payload

        export = client.get("/privacy/me/export", headers=headers)
        assert export.status_code == 200
        export_payload = export.json()
        assert export_payload["account"]["email"] == email
        assert len(export_payload["patients"]) == 1
        assert len(export_payload["reports"]) == 1
        assert len(export_payload["report_analyses"]) == 1
        assert export_payload["report_analyses"][0]["id"] == analysis.json()["id"]
        assert export_payload["report_analyses"][0]["summary"]["message"].endswith("This is not a diagnosis.")
        assert len(export_payload["medications"]) == 1
        assert export_payload["medications"][0]["name"] == "Metformin"
        assert len(export_payload["intakes"]) == 1
        assert export_payload["intakes"][0]["diet_style"] == "vegetarian"
        assert len(export_payload["care_plans"]) == 1
        assert export_payload["care_plans"][0]["id"] == care_plan.json()["id"]
        assert export_payload["care_plans"][0]["recommendation"]
        assert "storage_url" not in export_payload["reports"][0]

        delete_request = client.post(
            "/privacy/me/delete-request",
            json={"reason": "Testing deletion request"},
            headers=headers,
        )
        assert delete_request.status_code == 200
        assert delete_request.json()["status"] == "requested"

        delete_response = client.delete("/privacy/me", headers=headers)
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"

        blocked = client.get("/privacy/me/export", headers=headers)
        assert blocked.status_code == 401
