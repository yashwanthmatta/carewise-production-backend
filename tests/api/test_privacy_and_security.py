from fastapi.testclient import TestClient

from app.main import create_app
from tests.api.test_reports_and_access_control import auth_headers, create_profile


def test_security_headers_are_applied():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"


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

        export = client.get("/privacy/me/export", headers=headers)
        assert export.status_code == 200
        export_payload = export.json()
        assert export_payload["account"]["email"] == email
        assert len(export_payload["patients"]) == 1
        assert len(export_payload["reports"]) == 1

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
