from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import ReportAnalysis


def saved_report(client: TestClient) -> tuple[dict[str, str], str]:
    signup = client.post("/auth/signup", json={"email": f"pause-{uuid4().hex}@example.com", "password": "change-me-long-password"})
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    profile = client.put("/patients/me/profile", json={"name": "Test Patient", "date_of_birth": "1990-01-01"}, headers=headers)
    upload = client.post(
        "/reports/upload-file",
        data={"patient_id": profile.json()["patient_id"], "report_text": "Potassium 6.8 mmol/L 3.5-5.1"},
        files={"file": ("labs.txt", b"Potassium 6.8 mmol/L 3.5-5.1", "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 200
    return headers, upload.json()["id"]


def test_pause_switch_stops_server_explanations(monkeypatch):
    monkeypatch.setattr(settings, "report_explanations_paused", True)
    with TestClient(create_app()) as client:
        headers, report_id = saved_report(client)
        for response in (
            client.post(f"/reports/{report_id}/analyze", headers=headers),
            client.post("/analyze-report", json={"report_id": report_id}, headers=headers),
        ):
            assert response.status_code == 503
            assert "paused" in response.json()["detail"]
        # The report itself stays saved and readable; only the explanation is withheld.
        assert client.get(f"/reports/{report_id}/download", headers=headers).status_code == 200
    with SessionLocal() as db:
        assert db.scalars(select(ReportAnalysis).where(ReportAnalysis.report_id == report_id)).first() is None


def test_server_explanations_work_when_not_paused():
    with TestClient(create_app()) as client:
        headers, report_id = saved_report(client)
        assert client.post(f"/reports/{report_id}/analyze", headers=headers).status_code == 200
