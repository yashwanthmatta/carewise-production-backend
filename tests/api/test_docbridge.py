from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import LabPacket
from tests.api.test_reports_and_access_control import auth_headers


def make_clinic(client):
    headers, _ = auth_headers(client)
    clinic = client.post("/clinics", json={"name": "Maple Family Practice", "clinician_name": "Dr. Lee"}, headers=headers)
    assert clinic.status_code == 200
    return headers, clinic.json()["id"]


def draft(client, headers, clinic_id, value="148", lab_date="2026-10-01", ref="JD-1042"):
    response = client.post(
        f"/clinics/{clinic_id}/packets",
        json={
            "patient_ref": ref,
            "lab_date": lab_date,
            "markers": [{"name": "LDL cholesterol", "value": value, "unit": "mg/dL", "range": "<100", "status": "High"}],
            "summary": "Your LDL cholesterol is above the usual target.",
            "questions": ["What LDL goal fits me?"],
            "deidentified_confirmed": True,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_draft_approve_and_patient_view():
    with TestClient(create_app()) as client:
        headers, clinic_id = make_clinic(client)
        packet = draft(client, headers, clinic_id)
        assert packet["status"] == "draft"
        approved = client.post(
            f"/clinics/{clinic_id}/packets/{packet['id']}/approve",
            json={"summary": "Edited: your LDL is above target. We'll talk at your visit.", "questions": ["What LDL goal fits me?"]},
            headers=headers,
        )
        assert approved.status_code == 200
        body = approved.json()
        assert body["approved_by_name"] == "Dr. Lee"
        assert body["review_seconds"] is not None

        view = client.post("/clinics/packets/view", json={"token": body["patient_token"]})
        assert view.status_code == 200
        assert view.json()["clinic_name"] == "Maple Family Practice"
        assert view.json()["summary"].startswith("Edited")

        assert client.put(f"/clinics/{clinic_id}/packets/{packet['id']}", json={"summary": "x"}, headers=headers).status_code == 409
        metrics = client.get(f"/clinics/{clinic_id}/metrics", headers=headers).json()
        assert metrics["approved_this_week"] == 1
        assert metrics["patients_opened"] == 1

    with SessionLocal() as db:
        row = db.scalars(select(LabPacket)).one()
        assert "LDL" not in row.encrypted_markers
        assert "JD-1042" not in row.encrypted_patient_ref


def test_pilot_requires_deidentified_confirmation_and_drafts_are_not_public():
    with TestClient(create_app()) as client:
        headers, clinic_id = make_clinic(client)
        response = client.post(f"/clinics/{clinic_id}/packets", json={"patient_ref": "A1", "summary": "x"}, headers=headers)
        assert response.status_code == 422
        draft(client, headers, clinic_id)
        assert client.post("/clinics/packets/view", json={"token": "y" * 40}).status_code == 404


def test_other_clinics_cannot_see_packets():
    with TestClient(create_app()) as client:
        headers, clinic_id = make_clinic(client)
        packet = draft(client, headers, clinic_id)
        other_headers, _ = make_clinic(client)
        assert client.get(f"/clinics/{clinic_id}/packets", headers=other_headers).status_code == 404
        assert client.post(f"/clinics/{clinic_id}/packets/{packet['id']}/approve", json={"summary": "x"}, headers=other_headers).status_code == 404
        assert client.post("/clinics", json={"name": "Second", "clinician_name": "Dr. B"}, headers=headers).status_code == 409


def test_visit_summary_shows_what_changed():
    with TestClient(create_app()) as client:
        headers, clinic_id = make_clinic(client)
        draft(client, headers, clinic_id, value="162", lab_date="2026-06-01")
        draft(client, headers, clinic_id, value="148", lab_date="2026-10-01")
        summary = client.get(f"/clinics/{clinic_id}/patients/jd-1042/summary", headers=headers).json()
        assert len(summary["packets"]) == 2
        assert summary["changes"] == [{"name": "LDL cholesterol", "before": "162", "now": "148", "unit": "mg/dL", "status": "High"}]
        follow = client.post(f"/clinics/{clinic_id}/packets/{summary['packets'][0]['id']}/follow-up", headers=headers)
        assert follow.json()["status"] == "needs_call"


def test_deleting_account_removes_owned_clinic():
    with TestClient(create_app()) as client:
        headers, clinic_id = make_clinic(client)
        draft(client, headers, clinic_id)
        assert client.delete("/privacy/me", headers=headers).status_code == 200
    with SessionLocal() as db:
        assert db.scalars(select(LabPacket)).all() == []
