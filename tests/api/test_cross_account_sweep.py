"""Account access sweep (20 Nov 2026): one signed-in person can never read, change or analyse another
person's records through any route that takes a patient, report or sign-in id. Earlier tests cover
medications, care plans, upload and report text; this covers every remaining id-taking route, including
the older /upload-report, /analyze-report and /report-results paths. All data is synthetic."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app

REFUSED = {403, 404}


def account(client: TestClient, name: str) -> tuple[dict[str, str], str]:
    signup = client.post(
        "/auth/signup",
        json={"email": f"sweep-{uuid4().hex}@example.com", "password": "change-me-long-password", "role": "patient"},
    )
    assert signup.status_code == 200
    headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
    profile = client.put(
        "/patients/me/profile",
        json={
            "name": name,
            "date_of_birth": "1980-05-05",
            "sex_at_birth": "female",
            "conditions": "",
            "allergies": "None",
            "location_region": "US-CA",
            "insurance_status": "some",
        },
        headers=headers,
    )
    assert profile.status_code == 200
    return headers, profile.json()["patient_id"]


def test_no_route_lets_one_person_reach_another_persons_records():
    with TestClient(create_app()) as client:
        owner, owner_patient = account(client, "Synthetic Owner")
        other, _ = account(client, "Synthetic Other")

        report = client.post(
            "/reports/upload",
            json={
                "patient_id": owner_patient,
                "file_name": "synthetic.txt",
                "content_type": "text/plain",
                "report_text": "Sample Lab\nPotassium 4.2 mmol/L 3.5-5.1",
            },
            headers=owner,
        )
        assert report.status_code == 200
        report_id = report.json()["id"]
        assert client.post(f"/reports/{report_id}/analyze", headers=owner).status_code == 200
        trend = client.post(
            "/lab-trends",
            json={"patient_id": owner_patient, "test_name": "Potassium", "value": "4.2", "unit": "mmol/L", "observed_on": "2026-11-01"},
            headers=owner,
        )
        assert trend.status_code == 200
        # The owner's own requests work, so a refusal below means the check, not a broken request.
        assert client.get("/reports", params={"patient_id": owner_patient}, headers=owner).status_code == 200
        assert client.get(f"/reports/{report_id}/analyses", headers=owner).status_code == 200

        attempts = {
            "list reports": client.get("/reports", params={"patient_id": owner_patient}, headers=other),
            "legacy report results": client.get("/report-results", params={"patient_id": owner_patient}, headers=other),
            "list analyses": client.get(f"/reports/{report_id}/analyses", headers=other),
            "analyze": client.post(f"/reports/{report_id}/analyze", headers=other),
            "legacy analyze": client.post("/analyze-report", json={"report_id": report_id}, headers=other),
            "download": client.get(f"/reports/{report_id}/download", headers=other),
            "upload file": client.post(
                "/reports/upload-file",
                data={"patient_id": owner_patient, "report_text": "x"},
                files={"file": ("x.txt", b"x", "text/plain")},
                headers=other,
            ),
            "legacy upload": client.post(
                "/upload-report",
                data={"patient_id": owner_patient, "report_text": "x"},
                files={"file": ("x.txt", b"x", "text/plain")},
                headers=other,
            ),
            "read lab trends": client.get("/lab-trends", params={"patient_id": owner_patient}, headers=other),
            "add lab trend": client.post(
                "/lab-trends",
                json={"patient_id": owner_patient, "test_name": "Potassium", "value": "9.9", "unit": "mmol/L", "observed_on": "2026-11-02"},
                headers=other,
            ),
            "see care team": client.get(f"/patients/{owner_patient}/care-team", headers=other),
        }
        let_through = {name: r.status_code for name, r in attempts.items() if r.status_code not in REFUSED}
        assert not let_through, f"another person's records were reachable: {let_through}"
        # Nothing from the owner's report leaks in a refusal.
        for r in attempts.values():
            assert "Potassium" not in r.text and "Synthetic Owner" not in r.text

        # The owner's data is unchanged by the refused writes.
        trends = client.get("/lab-trends", params={"patient_id": owner_patient}, headers=owner).json()
        assert [t["value"] for t in trends] == ["4.2"]


def test_a_forged_or_missing_token_reaches_nothing():
    with TestClient(create_app()) as client:
        owner, owner_patient = account(client, "Synthetic Owner")
        for headers in ({}, {"Authorization": "Bearer not-a-real-token"}):
            assert client.get("/reports", params={"patient_id": owner_patient}, headers=headers).status_code == 401
            assert client.get("/patients/me/profile", headers=headers).status_code == 401
            assert client.get("/privacy/me/export", headers=headers).status_code == 401


def test_a_short_signing_key_is_named_in_a_warning_without_its_value(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "env", "production")
    monkeypatch.setattr(settings, "jwt_secret", "short-but-not-a-placeholder")
    assert settings.weak_secret_warnings() == ["CAREWISE_JWT_SECRET"]
    monkeypatch.setattr(settings, "jwt_secret", "x" * 48)
    assert settings.weak_secret_warnings() == []
    monkeypatch.setattr(settings, "env", "test")
    monkeypatch.setattr(settings, "jwt_secret", "short")
    assert settings.weak_secret_warnings() == []
