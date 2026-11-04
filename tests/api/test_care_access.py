"""Staff see a patient's records only through that patient's care-team grant. Synthetic data only."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import create_app
from app.models.carewise import CareAccessGrant, User
from tests.api.test_reports_and_access_control import auth_headers, create_profile

PASSWORD = "change-me-long-password"
DOC_A, DOC_B, ADMIN = "doc-a@clinic.example", "doc-b@clinic.example", "admin@followthrough.example"


@pytest.fixture(autouse=True)
def staff(monkeypatch):
    monkeypatch.setattr(settings, "staff_emails", f"{DOC_A}:clinician,{DOC_B}:clinician,{ADMIN}:admin")
    monkeypatch.setattr(settings, "staff_access_mode", "grants")


def staff_headers(client, email, role):
    response = client.post("/auth/signup", json={"email": email, "password": PASSWORD, "role": role})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        db.scalar(select(User).where(User.email == email)).email_verified = "true"
        db.commit()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def patient_with_records(client):
    headers, _ = auth_headers(client)
    patient_id = create_profile(client, headers)
    trend = client.post("/lab-trends", json={"patient_id": patient_id, "test_name": "Synthetic A1C", "value": "6.1", "unit": "%"}, headers=headers)
    assert trend.status_code == 200
    plan = client.post("/care-plans/generate", json={"patient_id": patient_id, "symptom_text": "synthetic dizziness when standing"}, headers=headers)
    assert plan.status_code == 200
    return headers, patient_id


PATIENT_READS = ["/lab-trends?patient_id={id}", "/reports?patient_id={id}"]


def readable(client, headers, patient_id):
    return [client.get(path.format(id=patient_id), headers=headers).status_code for path in PATIENT_READS]


def test_patients_cannot_read_each_other():
    with TestClient(create_app()) as client:
        _, patient_a = patient_with_records(client)
        headers_b, _ = patient_with_records(client)
        assert readable(client, headers_b, patient_a) == [403, 403]


def test_unassigned_clinician_and_admin_cannot_open_profiles():
    with TestClient(create_app()) as client:
        _, patient_id = patient_with_records(client)
        doctor = staff_headers(client, DOC_A, "clinician")
        admin = staff_headers(client, ADMIN, "admin")
        assert readable(client, doctor, patient_id) == [403, 403]
        assert readable(client, admin, patient_id) == [403, 403]
        # Administration still works, with counts only.
        assert client.get("/admin/summary", headers=admin).status_code == 200


def test_granted_clinician_can_read_until_revoked():
    with TestClient(create_app()) as client:
        patient_headers, patient_id = patient_with_records(client)
        doctor = staff_headers(client, DOC_A, "clinician")
        other_doctor = staff_headers(client, DOC_B, "clinician")
        grant = client.post(f"/patients/{patient_id}/care-team", json={"clinician_email": DOC_A}, headers=patient_headers).json()
        assert readable(client, doctor, patient_id) == [200, 200]
        assert readable(client, other_doctor, patient_id) == [403, 403]
        listed = client.get(f"/patients/{patient_id}/care-team", headers=patient_headers).json()["items"]
        assert [item["clinician_email"] for item in listed] == [DOC_A]

        revoked = client.delete(f"/patients/{patient_id}/care-team/{grant['id']}", headers=patient_headers)
        assert revoked.status_code == 200 and revoked.json()["revoked_at"]
        assert readable(client, doctor, patient_id) == [403, 403]  # immediately, same token


def test_expired_grant_stops_working():
    with TestClient(create_app()) as client:
        patient_headers, patient_id = patient_with_records(client)
        doctor = staff_headers(client, DOC_A, "clinician")
        grant = client.post(f"/patients/{patient_id}/care-team", json={"clinician_email": DOC_A, "days": 7}, headers=patient_headers).json()
        assert readable(client, doctor, patient_id) == [200, 200]
        with SessionLocal() as db:
            db.get(CareAccessGrant, grant["id"]).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
        assert readable(client, doctor, patient_id) == [403, 403]


def test_only_the_patient_manages_their_care_team():
    with TestClient(create_app()) as client:
        patient_headers, patient_id = patient_with_records(client)
        other_headers, _ = patient_with_records(client)
        doctor = staff_headers(client, DOC_A, "clinician")
        # A clinician cannot grant themselves access, and another patient cannot either.
        for headers in (doctor, other_headers):
            response = client.post(f"/patients/{patient_id}/care-team", json={"clinician_email": DOC_A}, headers=headers)
            assert response.status_code == 404
        assert readable(client, doctor, patient_id) == [403, 403]
        grant = client.post(f"/patients/{patient_id}/care-team", json={"clinician_email": DOC_A}, headers=patient_headers).json()
        assert client.delete(f"/patients/{patient_id}/care-team/{grant['id']}", headers=other_headers).status_code == 404
        assert client.get(f"/patients/{patient_id}/care-team", headers=doctor).status_code == 404


def test_only_verified_listed_clinicians_can_be_added():
    with TestClient(create_app()) as client:
        patient_headers, patient_id = patient_with_records(client)
        _, other_patient_email = auth_headers(client)
        staff_headers(client, ADMIN, "admin")
        unverified = client.post("/auth/signup", json={"email": DOC_B, "password": PASSWORD, "role": "clinician"})
        assert unverified.status_code == 200
        for email in (other_patient_email, ADMIN, DOC_B, "nobody@clinic.example"):
            response = client.post(f"/patients/{patient_id}/care-team", json={"clinician_email": email}, headers=patient_headers)
            assert response.status_code == 400
            assert response.json()["detail"] == "That address is not a FollowThrough Health clinician account."


def test_review_queue_lists_only_granted_patients():
    with TestClient(create_app()) as client:
        patient_headers, patient_id = patient_with_records(client)
        _, other_patient = patient_with_records(client)
        doctor = staff_headers(client, DOC_A, "clinician")
        admin = staff_headers(client, ADMIN, "admin")
        queue = lambda headers: {item["patient_id"] for item in client.get("/clinical-review/queue", headers=headers).json()["items"]}  # noqa: E731
        assert queue(doctor) == set()
        assert queue(admin) == set()
        client.post(f"/patients/{patient_id}/care-team", json={"clinician_email": DOC_A}, headers=patient_headers)
        assert queue(doctor) <= {patient_id}
        assert other_patient not in queue(doctor)


def test_reviewing_an_unassigned_care_plan_is_refused():
    with TestClient(create_app()) as client:
        patient_headers, patient_id = patient_with_records(client)
        doctor = staff_headers(client, DOC_A, "clinician")
        with SessionLocal() as db:
            from app.models.carewise import CarePlan

            plan_id = db.scalar(select(CarePlan.id).where(CarePlan.patient_id == patient_id))
        decision = {"status": "approved", "clinician_note": "synthetic"}
        assert client.post(f"/clinical-review/{plan_id}/review", json=decision, headers=doctor).status_code == 403
        assert client.post("/clinical-review/plan_does_not_exist/review", json=decision, headers=doctor).status_code == 404
        client.post(f"/patients/{patient_id}/care-team", json={"clinician_email": DOC_A}, headers=patient_headers)
        assert client.post(f"/clinical-review/{plan_id}/review", json=decision, headers=doctor).status_code == 200


def test_legacy_mode_restores_global_staff_access(monkeypatch):
    with TestClient(create_app()) as client:
        _, patient_id = patient_with_records(client)
        doctor = staff_headers(client, DOC_A, "clinician")
        assert readable(client, doctor, patient_id) == [403, 403]
        monkeypatch.setattr(settings, "staff_access_mode", "legacy_global")
        assert readable(client, doctor, patient_id) == [200, 200]


def test_forged_ids_do_not_leak():
    with TestClient(create_app()) as client:
        headers, _ = patient_with_records(client)
        assert client.get("/lab-trends?patient_id=patient_does_not_exist", headers=headers).status_code == 404
        assert client.get("/lab-trends?patient_id=' OR 1=1 --", headers=headers).status_code == 404
