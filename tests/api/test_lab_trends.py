from fastapi.testclient import TestClient

from app.main import create_app
from tests.api.test_reports_and_access_control import auth_headers, create_profile


def test_lab_trend_create_and_list_flow():
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)

        trend = client.post(
            "/lab-trends",
            json={
                "patient_id": patient_id,
                "test_name": "LDL cholesterol",
                "value": "142",
                "unit": "mg/dL",
                "observed_on": "2026-07-01",
                "flag": "high",
                "notes": "Saved from detected report values. Verify with original report.",
                "source": "detected_report_value",
            },
            headers=headers,
        )
        assert trend.status_code == 200
        trend_payload = trend.json()
        assert trend_payload["id"].startswith("lab_")
        assert trend_payload["test_name"] == "LDL cholesterol"
        assert trend_payload["notes"].startswith("Saved from detected")

        trends = client.get(f"/lab-trends?patient_id={patient_id}", headers=headers)
        assert trends.status_code == 200
        assert len(trends.json()) == 1
        assert trends.json()[0]["id"] == trend_payload["id"]


def test_lab_trends_require_patient_access():
    app = create_app()
    with TestClient(app) as client:
        owner_headers, _ = auth_headers(client)
        other_headers, _ = auth_headers(client)
        owner_patient_id = create_profile(client, owner_headers, "Owner Patient")
        create_profile(client, other_headers, "Other Patient")

        blocked_create = client.post(
            "/lab-trends",
            json={
                "patient_id": owner_patient_id,
                "test_name": "A1C",
                "value": "5.9",
                "unit": "%",
            },
            headers=other_headers,
        )
        assert blocked_create.status_code == 403

        blocked_list = client.get(f"/lab-trends?patient_id={owner_patient_id}", headers=other_headers)
        assert blocked_list.status_code == 403


def test_lab_trend_report_must_belong_to_patient():
    app = create_app()
    with TestClient(app) as client:
        owner_headers, _ = auth_headers(client)
        other_headers, _ = auth_headers(client)
        owner_patient_id = create_profile(client, owner_headers, "Owner Patient")
        other_patient_id = create_profile(client, other_headers, "Other Patient")

        upload = client.post(
            "/reports/upload",
            json={
                "patient_id": owner_patient_id,
                "file_name": "owner-report.txt",
                "content_type": "text/plain",
                "report_text": "LDL cholesterol elevated. No chest pain.",
            },
            headers=owner_headers,
        )
        assert upload.status_code == 200

        mismatch = client.post(
            "/lab-trends",
            json={
                "patient_id": other_patient_id,
                "report_id": upload.json()["id"],
                "test_name": "LDL cholesterol",
                "value": "142",
                "unit": "mg/dL",
            },
            headers=other_headers,
        )
        assert mismatch.status_code == 400


def test_lab_trends_are_in_privacy_export_and_summary():
    app = create_app()
    with TestClient(app) as client:
        headers, _ = auth_headers(client)
        patient_id = create_profile(client, headers)

        trend = client.post(
            "/lab-trends",
            json={
                "patient_id": patient_id,
                "test_name": "Vitamin D",
                "value": "22",
                "unit": "ng/mL",
                "flag": "needs_attention",
                "notes": "Educational tracking only.",
                "source": "manual",
            },
            headers=headers,
        )
        assert trend.status_code == 200

        summary = client.get("/privacy/me/export-summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["counts"]["lab_trends"] == 1

        export = client.get("/privacy/me/export", headers=headers)
        assert export.status_code == 200
        assert len(export.json()["lab_trends"]) == 1
        assert export.json()["lab_trends"][0]["notes"] == "Educational tracking only."
